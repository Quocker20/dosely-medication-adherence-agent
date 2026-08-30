"""Rejudge a saved live run without calling the chatbot again."""
from __future__ import annotations
import asyncio, json, os, sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.run_non_schedule_live import judge_hallucination


async def main():
    load_dotenv(ROOT / ".env")
    for key in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy"):
        os.environ.pop(key, None)
    source = Path(sys.argv[1])
    rows = json.loads(source.read_text(encoding="utf-8"))
    for index, row in enumerate(rows, start=1):
        try:
            verdict = await judge_hallucination(row, row)
            row["hallucination"] = verdict.model_dump()
        except Exception as exc:
            row["hallucination"] = {"applicable": True, "hallucinated": None, "confidence": 0,
                                      "unsupported_claims": [], "reason": f"judge_error: {type(exc).__name__}: {exc}"}
        print(f"[{index:03d}/100] {row['id']} hallucinated={row['hallucination']['hallucinated']}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = source.with_name(f"{source.stem}_rejudged_{stamp}.json")
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    flagged = [row for row in rows if row["hallucination"].get("hallucinated") is True]
    errors = [row for row in rows if row["hallucination"].get("hallucinated") is None]
    print(f"HALLUCINATION={len(flagged)}/{len(rows)} JUDGE_ERRORS={len(errors)} RESULT={output}")

if __name__ == "__main__":
    asyncio.run(main())
