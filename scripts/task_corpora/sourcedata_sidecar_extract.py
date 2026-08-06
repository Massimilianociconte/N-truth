"""Sidecar migration step 1: verify + unpack the official XML v2.0.3 archive.

Fail-closed: the archive must hash-verify against the SHA-256 recorded in the
merged C1.1 investigation before any XML is unpacked. Output: the extracted
XML directory and the deterministic upstream caption index JSONL.

Reads the immutable archive from the external volume; writes only inside the
temporary work directory given on the command line.

When ``--input-bundle-sha256`` is supplied, the extraction summary records it
so this stage report is bound to the same attested ProvenanceBuildInputs
bundle consumed by the build and validation stages.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ntruth.task_corpora.provenance_sidecar import (
    extract_xml_archive,
    iter_upstream_captions,
    sha256_file,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", type=Path)
    ap.add_argument("expected_sha256")
    ap.add_argument("work_dir", type=Path)
    ap.add_argument(
        "--input-bundle-sha256",
        default=None,
        help="bundle_sha256 of the attested ProvenanceBuildInputs, recorded in the summary",
    )
    args = ap.parse_args()

    xml_dir = args.work_dir / "xml_v2.0.3"
    extract_xml_archive(args.archive, xml_dir, expected_sha256=args.expected_sha256)
    index_path = args.work_dir / "upstream_caption_index.jsonl"
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
                "archive": str(args.archive),
                "archive_sha256": sha256_file(args.archive),
                "xml_files": len(list(xml_dir.glob("*.xml"))),
                "caption_rows": rows,
                "articles": len(articles),
                "index_path": str(index_path),
                "index_sha256": sha256_file(index_path),
                "input_bundle_sha256": args.input_bundle_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
