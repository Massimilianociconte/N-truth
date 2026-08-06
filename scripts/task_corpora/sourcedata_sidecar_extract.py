"""Sidecar migration step 1: verify + unpack the official XML v2.0.3 archive.

Fail-closed: the archive must hash-verify against the SHA-256 recorded in the
merged C1.1 investigation before any XML is unpacked. Output: the extracted
XML directory and the deterministic upstream caption index JSONL.

Reads the immutable archive from the external volume; writes only inside the
temporary work directory given on the command line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ntruth.task_corpora.provenance_sidecar import (
    extract_xml_archive,
    iter_upstream_captions,
    sha256_file,
)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(f"usage: {sys.argv[0]} ARCHIVE EXPECTED_SHA256 WORK_DIR")
    archive = Path(sys.argv[1])
    expected = sys.argv[2]
    work_dir = Path(sys.argv[3])
    xml_dir = work_dir / "xml_v2.0.3"
    extract_xml_archive(archive, xml_dir, expected_sha256=expected)
    index_path = work_dir / "upstream_caption_index.jsonl"
    rows = 0
    articles: set[str] = set()
    with index_path.open("w", encoding="utf-8") as out:
        for rec in iter_upstream_captions(xml_dir):
            out.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            rows += 1
            articles.add(rec["article_doi"])
    print(
        json.dumps(
            {
                "archive": str(archive),
                "archive_sha256": sha256_file(archive),
                "xml_files": len(list(xml_dir.glob("*.xml"))),
                "caption_rows": rows,
                "articles": len(articles),
                "index_path": str(index_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
