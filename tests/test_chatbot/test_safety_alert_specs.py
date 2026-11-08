"""TDD specs for lane S (agent-raised Red Alert, matching, latency). See docs/decision.md D07-D16."""

from __future__ import annotations

import asyncio
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.chatbot.graph import agent
from src.chatbot.nodes.safety_guard_node import EmergencyAssessment, safety_guard_node
from src.chatbot.nodes.scope_guard_node import ScopeClassification, scope_guard_node
from src.chatbot.semantic_plan import TOOL_TO_LEGACY_INTENT, SemanticPlan, SemanticStep
from src.chatbot.tools.safety_tools import match_severe_symptom_keyword, trigger_red_alert

PID = "patient-1"
NOTICE = "Dosely đã gửi cảnh báo tới bác sĩ của bạn."

_NOT_URGENT = EmergencyAssessment(urgent=False, confidence=0.1, reason="ok")
_URGENT = EmergencyAssessment(urgent=True, confidence=0.99, reason="nặng")


class FakeGate:
    """Redis stand-in: first SET NX wins, later ones return None."""

    def __init__(self, fail: bool = False) -> None:
        self.keys: set[str] = set()
        self.fail = fail
        self.calls = 0

    async def set(self, key, value, nx=False, ex=None):
        self.calls += 1
        if self.fail:
            raise ConnectionError("redis down")
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


def _safety_llm(assessment=_NOT_URGENT, captured: list | None = None):
    async def _invoke(prompt, *a, **k):
        if captured is not None:
            captured.append(prompt)
        return assessment

    return patch(
        "src.chatbot.nodes.safety_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": _invoke},
    )


def _prompt_text(prompt) -> str:
    if isinstance(prompt, str):
        return prompt
    return "\n".join(str(getattr(m, "content", m)) for m in prompt)


def _alert_env(stack: ExitStack, *, post=None, gate: FakeGate | None = None, authorized: bool = True):
    post = post if post is not None else AsyncMock(return_value={"id": "alert-1"})
    stack.enter_context(patch("src.chatbot.tools.safety_tools.post", post))
    stack.enter_context(
        patch("src.core.redis.get_redis_client", AsyncMock(return_value=gate if gate is not None else FakeGate()))
    )
    stack.enter_context(
        patch("src.chatbot.tool_authorization.get_actor_token", return_value="tok" if authorized else None)
    )
    stack.enter_context(
        patch(
            "src.chatbot.tool_authorization.decode_token",
            return_value={"type": "access", "role": "PATIENT", "sub": PID},
        )
    )
    return post


async def _run_node(text: str, *, assessment=_NOT_URGENT, post=None, gate=None, authorized=True, messages=None):
    with ExitStack() as stack:
        post = _alert_env(stack, post=post, gate=gate, authorized=authorized)
        stack.enter_context(_safety_llm(assessment))
        state = {"messages": messages or [HumanMessage(content=text)], "patient_id": PID}
        result = await safety_guard_node(state)
    return result, post


# ---------------------------------------------------------------- S-01
@pytest.mark.asyncio
async def test_keyword_escalation_sends_exactly_one_severe_symptom_alert():  # spec: S-01
    result, post = await _run_node("tôi bị co giật")
    assert result["escalated"] is True
    post.assert_awaited_once()
    assert post.await_args.args[0] == f"/patients/{PID}/sos"
    assert post.await_args.kwargs["json"]["triggered_by_type"] == "SEVERE_SYMPTOM"


@pytest.mark.asyncio
async def test_llm_escalation_sends_one_alert():  # spec: S-01
    result, post = await _run_node("người tôi lịm dần đi, không biết sao nữa", assessment=_URGENT)
    assert result["escalated"] is True
    post.assert_awaited_once()
    assert post.await_args.kwargs["json"]["triggered_by_type"] == "SEVERE_SYMPTOM"


@pytest.mark.asyncio
async def test_benign_turn_sends_no_alert():  # spec: S-01
    result, post = await _run_node("hôm nay tôi uống thuốc chưa nhỉ")
    assert result["escalated"] is False
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_medication_policy_block_sends_no_alert():  # spec: S-01
    result, post = await _run_node("Tôi tăng gấp đôi liều được không?")
    assert result["safety_blocked"] is True
    post.assert_not_awaited()


# ---------------------------------------------------------------- S-02
@pytest.mark.asyncio
async def test_second_escalation_within_gate_window_sends_no_new_alert():  # spec: S-02
    gate = FakeGate()
    post = AsyncMock(return_value={"id": "a"})
    first, _ = await _run_node("tôi bị co giật", post=post, gate=gate)
    second, _ = await _run_node("tôi bị khó thở", post=post, gate=gate)
    assert first["escalated"] and second["escalated"]
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_redis_failure_still_sends_alert_fail_open():  # spec: S-02
    result, post = await _run_node("tôi bị co giật", gate=FakeGate(fail=True))
    assert result["escalated"] is True
    post.assert_awaited_once()


# ---------------------------------------------------------------- S-03
@pytest.mark.asyncio
async def test_idempotency_key_independent_of_matched_keyword():  # spec: S-03
    fixed = datetime(2026, 11, 8, 10, 1, 0, tzinfo=UTC)
    keys = []
    for text in ("tôi bị tức ngực", "tôi bị khó thở"):
        post = AsyncMock(return_value={})
        with patch("src.chatbot.tools.idempotency.datetime") as dt:
            dt.now.return_value = fixed
            await _run_node(text, post=post, gate=FakeGate())
        keys.append(post.await_args.kwargs["headers"]["Idempotency-Key"])
    assert keys[0] == keys[1]


# ---------------------------------------------------------------- S-04
@pytest.mark.asyncio
async def test_alert_send_failure_never_blocks_reply():  # spec: S-04
    post = AsyncMock(side_effect=RuntimeError("backend down"))
    result, _ = await _run_node("tôi bị co giật", post=post)
    assert result["escalated"] is True
    assert result["messages"] and "115" in result["messages"][0].content


# ---------------------------------------------------------------- S-05
@pytest.mark.parametrize(
    "text",
    [
        "tôi bị khó thở",
        "tôi bị đau ngực",
        "con tôi co giật",
        "bà vừa ngất",
        "tôi muốn chết",
        "tôi nôn ra máu",
        "bị sưng môi",
    ],
)
@pytest.mark.asyncio
async def test_life_threatening_keywords_send_critical(text):  # spec: S-05
    result, post = await _run_node(text)
    assert result["escalated"] is True
    assert post.await_args.kwargs["json"]["severity"] == "CRITICAL"


@pytest.mark.parametrize(
    "text",
    ["người tôi bị phát ban", "tôi nổi mề đay", "tôi sốt cao không hạ", "tôi đau đầu dữ dội"],
)
@pytest.mark.asyncio
async def test_other_keywords_send_high(text):  # spec: S-05
    result, post = await _run_node(text)
    assert result["escalated"] is True
    assert post.await_args.kwargs["json"]["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_llm_only_detection_sends_high():  # spec: S-05
    result, post = await _run_node("người tôi lịm dần đi, không biết sao nữa", assessment=_URGENT)
    assert result["escalated"] is True
    assert post.await_args.kwargs["json"]["severity"] == "HIGH"


# ---------------------------------------------------------------- S-06
@pytest.mark.parametrize("text", ["tôi không khó thở", "hết đau ngực rồi", "không còn co giật"])
def test_negated_keyword_does_not_match(text):  # spec: S-06
    assert match_severe_symptom_keyword(text) is None


def test_negation_elsewhere_does_not_cancel_keyword():  # spec: S-06
    assert match_severe_symptom_keyword("tôi không ngủ được và đau ngực") == "đau ngực"


def test_keyword_containing_negation_word_still_matches():  # spec: S-06
    assert match_severe_symptom_keyword("thở không ra hơi") == "thở không ra hơi"


# ---------------------------------------------------------------- S-07
@pytest.mark.parametrize("text", ["toi bi kho tho", "dau nguc qua"])
def test_unaccented_multi_syllable_keywords_match(text):  # spec: S-07
    assert match_severe_symptom_keyword(text) is not None


@pytest.mark.parametrize("text", ["doi mot xiu", "cho toi ngat nghi chut"])
def test_unaccented_single_syllable_collisions_do_not_match(text):  # spec: S-07
    assert match_severe_symptom_keyword(text) is None


# ---------------------------------------------------------------- S-08
@pytest.mark.asyncio
async def test_emergency_llm_receives_last_three_human_messages():  # spec: S-08
    captured: list = []
    messages = [
        HumanMessage(content="tôi thấy người lịm lịm từ sáng"),
        AIMessage(content="Bạn nghỉ ngơi nhé"),
        HumanMessage(content="giờ còn hơi choáng"),
        AIMessage(content="ok"),
        HumanMessage(content="cảm ơn"),
    ]
    with ExitStack() as stack:
        _alert_env(stack)
        stack.enter_context(_safety_llm(_NOT_URGENT, captured))
        await safety_guard_node({"messages": messages, "patient_id": PID})
    assert captured, "emergency LLM was not called"
    text = _prompt_text(captured[0])
    assert "lịm lịm từ sáng" in text
    assert "cảm ơn" in text


@pytest.mark.asyncio
async def test_keyword_layer_ignores_earlier_messages():  # spec: S-08
    messages = [HumanMessage(content="tôi đau ngực"), AIMessage(content="hãy gọi 115"), HumanMessage(content="cảm ơn")]
    result, post = await _run_node("", messages=messages)
    assert result["escalated"] is False
    post.assert_not_awaited()


# ---------------------------------------------------------------- S-09
@pytest.mark.asyncio
async def test_trigger_red_alert_requires_emergency_authorization():  # spec: S-09
    with ExitStack() as stack:
        post = _alert_env(stack, authorized=False)
        await trigger_red_alert.ainvoke(
            {"patient_id": PID, "reason": "SEVERE_SYMPTOM: tức ngực", "severity": "CRITICAL", "evidence": "x"}
        )
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_red_alert_rejects_other_patients_token():  # spec: S-09
    with ExitStack() as stack:
        post = _alert_env(stack)
        await trigger_red_alert.ainvoke(
            {
                "patient_id": "someone-else",
                "reason": "SEVERE_SYMPTOM: tức ngực",
                "severity": "CRITICAL",
                "evidence": "x",
            }
        )
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_node_without_authorization_sends_nothing_but_still_escalates():  # spec: S-09
    result, post = await _run_node("tôi bị co giật", authorized=False)
    assert result["escalated"] is True
    assert "115" in result["messages"][0].content
    post.assert_not_awaited()


# ---------------------------------------------------------------- S-10
@pytest.mark.asyncio
async def test_trigger_red_alert_failure_text_has_no_raw_exception():  # spec: S-10
    with ExitStack() as stack:
        _alert_env(stack, post=AsyncMock(side_effect=Exception("secret-db-host:5432")))
        text = await trigger_red_alert.ainvoke(
            {"patient_id": PID, "reason": "SEVERE_SYMPTOM: tức ngực", "severity": "CRITICAL", "evidence": "x"}
        )
    assert "secret-db-host" not in text


# ---------------------------------------------------------------- graph helpers
def _scope_llm(result: ScopeClassification | None = None, delay: float = 0.0):
    result = result or ScopeClassification(category="medication", reason="t", confidence=1.0)

    async def _invoke(*a, **k):
        if delay:
            await asyncio.sleep(delay)
        return result

    return patch(
        "src.chatbot.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": _invoke},
    )


def _refusal(reply="Hãy gọi 115 ngay."):
    return patch(
        "src.chatbot.nodes.refusal_response.get_llm",
        **{"return_value.ainvoke": AsyncMock(return_value=AIMessage(content=reply))},
    )


def _general_plan():
    tool = next(t for t, i in TOOL_TO_LEGACY_INTENT.items() if i == "general")
    plan = SemanticPlan(
        purpose="t", steps=[SemanticStep(id="step_1", tool=tool, purpose="t", confidence=0.99)], confidence=0.99
    )
    return patch(
        "src.chatbot.nodes.semantic_planner_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=plan)},
    )


# ---------------------------------------------------------------- S-11
@pytest.mark.asyncio
async def test_final_reply_ends_with_doctor_notified_sentence_when_alert_sent():  # spec: S-11
    with ExitStack() as stack:
        _alert_env(stack)
        stack.enter_context(_safety_llm())
        stack.enter_context(_refusal())
        result = await agent.ainvoke({"messages": [HumanMessage(content="tôi bị co giật")], "patient_id": PID})
    assert result["messages"][-1].content.rstrip().endswith(NOTICE)


@pytest.mark.asyncio
async def test_final_reply_has_notice_when_gate_says_alert_already_exists():  # spec: S-11
    gate = FakeGate()
    post = AsyncMock(return_value={})
    with ExitStack() as stack:
        _alert_env(stack, post=post, gate=gate)
        stack.enter_context(_safety_llm())
        stack.enter_context(_refusal())
        # Burn the gate with a first escalation, then run the real turn.
        await agent.ainvoke({"messages": [HumanMessage(content="tôi bị khó thở")], "patient_id": PID})
        result = await agent.ainvoke({"messages": [HumanMessage(content="tôi bị co giật")], "patient_id": PID})
    assert post.await_count == 1
    assert result["messages"][-1].content.rstrip().endswith(NOTICE)


@pytest.mark.asyncio
async def test_final_reply_has_no_notice_when_alert_failed():  # spec: S-11
    with ExitStack() as stack:
        _alert_env(stack, post=AsyncMock(side_effect=RuntimeError("down")))
        stack.enter_context(_safety_llm())
        stack.enter_context(_refusal())
        result = await agent.ainvoke({"messages": [HumanMessage(content="tôi bị co giật")], "patient_id": PID})
    assert NOTICE not in result["messages"][-1].content


# ---------------------------------------------------------------- S-12
@pytest.mark.parametrize("text", ["thuốc dmso dùng thế nào", "tôi hỏi admin về thuốc huyết áp"])
@pytest.mark.asyncio
async def test_dm_inside_a_word_is_not_abusive_precheck(text):  # spec: S-12
    with patch("src.chatbot.nodes.scope_guard_node.get_llm") as llm:
        result = await scope_guard_node({"messages": [HumanMessage(content=text)], "patient_id": PID})
    assert result["scope_blocked"] is False
    assert result["scope_category"] == "medication"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_standalone_dm_is_still_not_whitelisted_and_can_be_blocked():  # spec: S-12
    abusive = ScopeClassification(category="abusive_noise", reason="t", confidence=1.0)
    with _scope_llm(abusive):
        result = await scope_guard_node({"messages": [HumanMessage(content="dm thuốc này")], "patient_id": PID})
    assert result["scope_blocked"] is True


# ---------------------------------------------------------------- S-13
@pytest.mark.asyncio
async def test_safety_and_scope_llms_run_concurrently():  # spec: S-13
    async def _slow(*a, **k):
        await asyncio.sleep(0.3)
        return _NOT_URGENT

    slow_safety = AsyncMock(side_effect=_slow)
    chat = AIMessage(content="Mình có thể hỗ trợ.")
    with ExitStack() as stack:
        _alert_env(stack)
        stack.enter_context(
            patch(
                "src.chatbot.nodes.safety_guard_node.get_llm",
                **{"return_value.with_structured_output.return_value.ainvoke": slow_safety},
            )
        )
        stack.enter_context(_scope_llm(delay=0.3))
        stack.enter_context(_general_plan())
        chat_llm = stack.enter_context(patch("src.chatbot.nodes.chat_node.get_llm"))
        chat_llm.return_value.ainvoke = AsyncMock(return_value=chat)
        start = time.perf_counter()
        await agent.ainvoke({"messages": [HumanMessage(content="người tôi cứ lâng lâng sao ấy")], "patient_id": PID})
        elapsed = time.perf_counter() - start
    assert slow_safety.await_count >= 1
    assert elapsed < 0.5, f"safety+scope took {elapsed:.2f}s (sequential?)"


@pytest.mark.asyncio
async def test_scope_result_ignored_when_safety_escalates():  # spec: S-13
    out_of_scope = ScopeClassification(category="out_of_scope", reason="t", confidence=1.0)
    with ExitStack() as stack:
        _alert_env(stack)
        stack.enter_context(_safety_llm(_URGENT))
        stack.enter_context(_scope_llm(out_of_scope, delay=0.05))
        stack.enter_context(_refusal("Hãy gọi 115 ngay."))
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="người tôi lịm dần đi, không biết sao nữa")], "patient_id": PID}
        )
    assert result["escalated"] is True
    assert result["refusal_reason"].startswith("SEVERE_SYMPTOM")
    assert not result.get("scope_blocked")
