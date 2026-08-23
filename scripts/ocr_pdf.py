"""Convert a scanned PDF to a searchable PDF and a UTF-8 text sidecar.

This is a small, resumable-friendly wrapper around OCRmyPDF. For very large
books, use --pages to process a page range into a separate output file.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCR a scanned PDF with Vietnamese and English recognition."
    )
    parser.add_argument("input", type=Path, help="Source scanned PDF")
    parser.add_argument("output", type=Path, help="Searchable PDF to create")
    parser.add_argument(
        "--sidecar",
        type=Path,
        help="Extracted UTF-8 text (default: output name with .txt suffix)",
    )
    parser.add_argument(
        "--pages",
        help="Optional OCRmyPDF page range, for example 1-100 or 101-200",
    )
    parser.add_argument("--jobs", type=int, default=2, help="Parallel OCR workers")
    parser.add_argument("--output-type", choices=("pdf", "pdfa"), default="pdf")
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace an existing output"
    )
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    sidecar = (args.sidecar or output.with_suffix(".txt")).resolve()

    if not source.is_file():
        fail(f"input PDF does not exist: {source}")
    if source.suffix.lower() != ".pdf" or output.suffix.lower() != ".pdf":
        fail("input and output must both use the .pdf extension")
    if source == output:
        fail("output must be different from input; the source is never modified")
    if output.exists() and not args.overwrite:
        fail(f"output already exists: {output} (use --overwrite to replace it)")
    if sidecar == output or sidecar == source:
        fail("sidecar must be a separate file")
    if args.jobs < 1:
        fail("--jobs must be at least 1")

    try:
        subprocess.run(
            [sys.executable, "-m", "ocrmypdf", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        fail(
            "OCRmyPDF is not installed or not on PATH. Follow docs/rag_ocr.md "
            "to install OCRmyPDF, Tesseract, Ghostscript, and Vietnamese data."
        )

    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parent.parent
    ascii_tessdata = Path(r"C:\OCRTools\tessdata")
    local_tessdata = repo_root / ".tools" / "tessdata"
    if ascii_tessdata.is_dir():
        env["TESSDATA_PREFIX"] = str(ascii_tessdata)
    elif local_tessdata.is_dir():
        env["TESSDATA_PREFIX"] = str(local_tessdata)

    tesseract_dir = Path(r"C:\Program Files\Tesseract-OCR")
    if tesseract_dir.is_dir():
        env["PATH"] = f"{tesseract_dir}{os.pathsep}{env.get('PATH', '')}"

    gs_roots = sorted(Path(r"C:\Program Files\gs").glob("gs*\\bin"), reverse=True)
    conda_gs = Path(r"C:\OCRTools\gsenv\Library\bin")
    if conda_gs.is_dir():
        gs_roots.insert(0, conda_gs)
    if gs_roots:
        env["PATH"] = f"{gs_roots[0]}{os.pathsep}{env.get('PATH', '')}"

    output.parent.mkdir(parents=True, exist_ok=True)
    sidecar.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "ocrmypdf",
        "--force-ocr",  # Pages contain only a watermark text layer over scan images.
        "--language",
        "vie+eng",
        "--rotate-pages",
        "--deskew",
        "--optimize",
        "1",
        "--jobs",
        str(args.jobs),
        "--output-type",
        args.output_type,
        "--sidecar",
        str(sidecar),
    ]
    if args.pages:
        command.extend(("--pages", args.pages))
    if args.overwrite:
        command.append("--force")
    command.extend((str(source), str(output)))

    print("Starting OCR. The source file will not be modified.")
    print(f"Input:   {source}")
    print(f"PDF:     {output}")
    print(f"Text:    {sidecar}")
    subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
