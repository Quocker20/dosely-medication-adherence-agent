"""Run the unified chatbot golden set through the real LangGraph agent.

Optional filters:
  GOLDEN_IDS=GRD-001,RAG-001
  GOLDEN_CATEGORIES=emergency,schedule_today
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.graph import agent
from src.core.security import create_access_token, reset_actor_token, set_actor_token

ROOT = Path(__file__).resolve().parents[1]


def _selected(cases: list[dict]) -> list[dict]:
    ids = {value.strip() for value in os.getenv("GOLDEN_IDS", "").split(",") if value.strip()}
    categories = {
        value.strip() for value in os.getenv("GOLDEN_CATEGORIES", "").split(",") if value.strip()
    }
    if ids:
        cases = [case for case in cases if case["id"] in ids]
    if categories:
        cases = [case for case in cases if case["category"] in categories]
    return cases


def _actual_disposition(state: dict) -> str:
    if state.get("escalated"):
        return "escalated"
    if (
        state.get("scope_blocked")
        or state.get("safety_blocked")
        or state.get("refusal_reason")
        or state.get("output_errors")
    ):
        return "blocked"
    if state.get("intent") == "clarify" or (state.get("intent_analysis") or {}).get("needs_clarification"):
        return "clarification"
    return "allowed"


def evaluate_case(case: dict, state: dict) -> tuple[bool, list[str]]:
    expected = case["expected"]
    actual_disposition = _actual_disposition(state)
    errors: list[str] = []
    wanted_disposition = expected["disposition"]
    if wanted_disposition == "grounded_or_safe_refusal":
        safe_refusal = actual_disposition == "blocked" and bool(
            state.get("refusal_reason") or state.get("output_errors")
        )
        grounded_answer = actual_disposition == "allowed" and state.get("grounding_valid") is True
        if not (safe_refusal or grounded_answer):
            errors.append(
                f"expected grounded answer or safe refusal, got disposition={actual_disposition}, "
                f"grounding={state.get('grounding_valid')}"
            )
    elif wanted_disposition == "blocked_or_clarification":
        if actual_disposition not in {"blocked", "clarification"}:
            errors.append(f"disposition={actual_disposition}")
    elif actual_disposition != wanted_disposition:
        errors.append(f"disposition={actual_disposition}, expected={wanted_disposition}")

    intents = expected.get("intents") or []
    if intents and state.get("intent") not in intents:
        errors.append(f"intent={state.get('intent')}, expected one of {intents}")
    if expected.get("grounding") is True and state.get("grounding_valid") is not True:
        errors.append(f"grounding_valid={state.get('grounding_valid')}")
    if expected.get("reference_type"):
        actual_reference = (state.get("intent_analysis") or {}).get("reference_type")
        if actual_reference != expected["reference_type"]:
            errors.append(f"reference_type={actual_reference}")
    if expected.get("reason"):
        actual_reason = state.get("refusal_reason") or state.get("safety_reason")
        if actual_reason != expected["reason"]:
            errors.append(f"reason={actual_reason}, expected={expected['reason']}")
    answer = str((state.get("messages") or [AIMessage(content="")])[-1].content)
    if not answer.strip():
        errors.append("empty_answer")
    for phrase in expected.get("answer_contains") or []:
        if phrase.casefold() not in answer.casefold():
            errors.append(f"answer missing {phrase!r}")
    return not errors, errors


async def _run_case(case: dict) -> dict:
    messages = []
    turns = case.get("turns") or [case["question"]]
    state: dict = {}
    patient_id = "11111111-1111-1111-1111-111111111111"
    token = create_access_token(user_id=patient_id, role="PATIENT", phone_number="golden-test")
    handle = set_actor_token(token)
    try:
        for turn in turns:
            messages.append(HumanMessage(content=turn))
            state = await asyncio.wait_for(
                agent.ainvoke({
                    "messages": messages,
                    "patient_id": patient_id,
                    "client_date": "2026-09-01",
                    "client_datetime": "2026-09-01T12:00:00+07:00",
                }),
                timeout=60,
            )
            messages = list(state.get("messages") or messages)
    finally:
        reset_actor_token(handle)
    passed, errors = evaluate_case(case, state)
    return {
        **case,
        "passed": passed,
        "failures": errors,
        "actual": {
            "disposition": _actual_disposition(state),
            "intent": state.get("intent"),
            "refusal_reason": state.get("refusal_reason"),
            "grounding_valid": state.get("grounding_valid"),
            "reference_type": (state.get("intent_analysis") or {}).get("reference_type"),
            "output_errors": state.get("output_errors") or [],
            "answer": str((state.get("messages") or [AIMessage(content="")])[-1].content),
        },
    }


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    cases = _selected(json.loads(
        (ROOT / "eval/chatbot_full_golden_cases.json").read_text(encoding="utf-8")
    ))
    rows = []
    for index, case in enumerate(cases, start=1):
        print(f"RUN {index}/{len(cases)} {case['id']} {case['category']}", flush=True)
        try:
            rows.append(await _run_case(case))
        except Exception as error:
            rows.append({
                **case, "passed": False,
                "failures": [f"{type(error).__name__}: {error}"],
                "actual": {},
            })
    output = ROOT / "eval/results" / f"chatbot_full_golden_{datetime.now():%Y%m%d_%H%M%S}.json"
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(row["passed"] for row in rows)
    print(f"SCORE={passed}/{len(rows)} RESULT={output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
