"""Split a PDF into deterministic, resumable page-range parts."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pages-per-part", type=int, default=15)
    args = parser.parse_args()
    if args.pages_per_part < 1:
        raise SystemExit("--pages-per-part must be at least 1")

    source = args.input.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise SystemExit(f"Input does not exist: {source}")
    output.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(source)
    total = len(reader.pages)
    expected_names: set[str] = set()
    for part, start in enumerate(range(0, total, args.pages_per_part), start=1):
        end = min(start + args.pages_per_part, total)
        name = f"part-{part:03d}-pages-{start + 1:03d}-{end:03d}.pdf"
        expected_names.add(name)
        destination = output / name
        if destination.exists():
            print(f"[{part}] SKIP {name}", flush=True)
            continue
        writer = PdfWriter()
        for page_number in range(start, end):
            writer.add_page(reader.pages[page_number])
        temporary = destination.with_suffix(".pdf.tmp")
        with temporary.open("wb") as handle:
            writer.write(handle)
        temporary.replace(destination)
        print(f"[{part}] WROTE {name}", flush=True)

    unexpected = sorted(path.name for path in output.glob("part-*.pdf") if path.name not in expected_names)
    if unexpected:
        raise SystemExit(f"Unexpected existing part files: {unexpected}")
    print(f"Complete: {total} pages in {len(expected_names)} parts")


if __name__ == "__main__":
    main()
