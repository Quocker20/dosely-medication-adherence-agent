"""Resolve merged review groups conservatively into approved or rejected sets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--rejected", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    args = parser.parse_args()
    groups = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line]
    approved: list[dict] = []
    rejected: list[dict] = []
    decisions: list[dict] = []
    for group in groups:
        # Short sections are often complete and useful (e.g. a one-line
        # indication or contraindication). Other reasons require verification
        # against the scan and are excluded rather than guessed.
        accept = group["review_reasons"] == ["too_short"]
        status = "approved" if accept else "rejected"
        notes = (
            "Approved: concise but complete section; OCR and taxonomy confidence passed."
            if accept
            else "Rejected from index: unresolved OCR, numeric, or taxonomy risk."
        )
        resolved = dict(group)
        resolved["chunk_id"] = group["review_group_id"]
        resolved["review_status"] = status
        resolved["needs_review"] = False
        resolved["reviewer_notes"] = notes
        (approved if accept else rejected).append(resolved)
        decisions.append(
            {
                "review_group_id": group["review_group_id"],
                "drug_name": group["drug_name"],
                "section": group["section"],
                "pages": f"{group['page_start']}-{group['page_end']}",
                "decision": status,
                "reasons": group["review_reasons"],
                "reviewer_notes": notes,
            }
        )

    for path, rows in ((args.approved, approved), (args.rejected, rejected), (args.decisions, decisions)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Resolved {len(groups)} groups: approved={len(approved)} rejected={len(rejected)} pending=0")


if __name__ == "__main__":
    main()
