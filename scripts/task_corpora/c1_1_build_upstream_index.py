"""C1.1 PoC step 1: build upstream caption index from SourceData XML v2.0.3.

Reads the official xml_v2.0.3 corpus and emits one JSON line per caption text:
  {article_doi, fig_id, fig_label, panel_id, caption}

Normalization policy is documented in normalize_caption(). Output is
deterministic given identical input XML files (sorted iteration).

Research artefact for C1.1 investigation; operates only on files under the
temporary investigation directory, never on canonical SourceData paths.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_WS = re.compile(r"\s+")


def normalize_caption(text: str) -> str:
    """Canonical whitespace normalization only (no case folding, no punctuation change)."""
    return _WS.sub(" ", text).strip()


def caption_text_from_element(el: ET.Element) -> str:
    """Recover caption text of an element, substituting sd-tag wrappers with their text."""
    parts: list[str] = []

    def walk(node: ET.Element) -> None:
        if node.tag == "sd-tag":
            parts.append(node.get("text") or "")
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return normalize_caption("".join(parts))


def iter_upstream_captions(xml_dir: Path):
    files = sorted(xml_dir.glob("*.xml"))
    for fp in files:
        root = ET.parse(fp).getroot()
        doi = root.get("doi", "")
        for fig in root.iter("fig"):
            fig_id = fig.get("id", "")
            label_el = fig.find("label")
            fig_label = normalize_caption(label_el.text or "") if label_el is not None else ""
            panels = list(fig.iter("sd-panel"))
            if panels:
                for panel in panels:
                    yield {
                        "article_doi": doi,
                        "fig_id": fig_id,
                        "fig_label": fig_label,
                        "panel_id": panel.get("panel_id", ""),
                        "caption": caption_text_from_element(panel),
                    }
            else:
                yield {
                    "article_doi": doi,
                    "fig_id": fig_id,
                    "fig_label": fig_label,
                    "panel_id": "",
                    "caption": caption_text_from_element(fig),
                }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} XML_DIR OUT_JSONL")
    xml_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    rows = 0
    files = sorted(xml_dir.glob("*.xml"))
    with out_path.open("w", encoding="utf-8") as out:
        for rec in iter_upstream_captions(xml_dir):
            out.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            rows += 1
    print(json.dumps({"files": len(files), "caption_rows": rows, "out": str(out_path)}))


if __name__ == "__main__":
    main()
