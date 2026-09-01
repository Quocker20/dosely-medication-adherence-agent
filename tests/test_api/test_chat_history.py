import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.core.security import create_access_token, hash_password
from src.modules.agents.models import ChatConversation, ChatMessage
from src.modules.agents.repository import generate_conversation_title
from src.modules.auth.models import User
from src.modules.patients.models import PatientProfile

PATIENT_1_PHONE = "+84900888001"
PATIENT_2_PHONE = "+84900888002"
PIN = "123456"

_TEST_PHONES = [PATIENT_1_PHONE, PATIENT_2_PHONE]


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[str] = []
        self.unlink_calls: list[tuple[str, ...]] = []

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.set_calls.append(key)
        self.store[key] = value

    async def scan_iter(self, match: str, count: int = 200):
        prefix = match[:-1] if match.endswith("*") else match
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    async def unlink(self, *keys: str) -> None:
        self.unlink_calls.append(tuple(keys))
        for key in keys:
            self.store.pop(key, None)


async def _purge_test_data() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            ids = (await db.execute(select(User.id).where(User.phone.in_(_TEST_PHONES)))).scalars().all()
            if not ids:
                return
            conv_ids = (
                (await db.execute(select(ChatConversation.id).where(ChatConversation.patient_id.in_(ids))))
                .scalars()
                .all()
            )
            if conv_ids:
                await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(conv_ids)))
                await db.execute(delete(ChatConversation).where(ChatConversation.id.in_(conv_ids)))
            await db.execute(delete(PatientProfile).where(PatientProfile.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate():
    await engine.dispose()
    await _purge_test_data()
    yield
    await _purge_test_data()
    await engine.dispose()


async def _create_patient(phone: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = User(
                phone=phone,
                role="PATIENT",
                status="ACTIVE",
                hashed_password=hash_password(PIN),
            )
            db.add(user)
            await db.flush()
            profile = PatientProfile(
                user_id=user.id,
                name="Patient Test",
                timezone="Asia/Ho_Chi_Minh",
            )
            db.add(profile)
            await db.flush()
            return user.id


def _auth_headers(user_id: uuid.UUID, phone: str, role: str = "PATIENT") -> dict[str, str]:
    token = create_access_token(
        user_id=str(user_id),
        role=role,
        phone_number=phone,
    )
    return {"Authorization": f"Bearer {token}"}


def test_generate_conversation_title_helper():
    assert generate_conversation_title("") == "Cuộc trò chuyện mới"
    assert generate_conversation_title("   ") == "Cuộc trò chuyện mới"
    assert (
        generate_conversation_title("  Thuốc này uống   sau ăn  đúng không?  ") == "Thuốc này uống sau ăn đúng không?"
    )
    long_msg = "A" * 80
    res = generate_conversation_title(long_msg, max_length=30)
    assert len(res) <= 30
    assert res.endswith("...")


def test_database_snapshot_uses_canonical_chat_tables_only():
    sql = Path("docs/database_v1_init.sql").read_text(encoding="utf-8")
    migration = Path("alembic/versions/0026_drop_legacy_conversations.py").read_text(encoding="utf-8")

    assert "CREATE TABLE chat_conversations" in sql
    assert "CREATE TABLE chat_messages" in sql
    assert "INSERT INTO alembic_version(version_num) VALUES ('0026_drop_legacy_conversations')" in sql
    assert "CREATE TABLE conversations" not in sql
    assert "CREATE TABLE messages" not in sql
    assert migration.index("DROP TABLE IF EXISTS messages") < migration.index("DROP TABLE IF EXISTS conversations")


@pytest.mark.asyncio
async def test_chat_creates_conversation_and_sets_summary(client):
    patient_id = await _create_patient(PATIENT_1_PHONE)
    headers = _auth_headers(patient_id, PATIENT_1_PHONE)

    mock_agent_result = {
        "messages": [AsyncMock(content="Thuốc uống sau ăn nhé")],
        "intent": "MEDICATION_QUERY",
    }
    with patch("src.modules.agents.service.agent.ainvoke", new=AsyncMock(return_value=mock_agent_result)):
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Tôi nên uống thuốc trước hay sau ăn?"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["response"] == "Thuốc uống sau ăn nhé"
    conv_id = data.get("conversationId")
    assert conv_id is not None

    # Check conversation exists in database with summary
    async with AsyncSessionLocal() as db:
        conv = await db.get(ChatConversation, uuid.UUID(conv_id))
        assert conv is not None
        assert conv.summary == "Tôi nên uống thuốc trước hay sau ăn?"
        messages = (await db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv.id))).all()
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Tôi nên uống thuốc trước hay sau ăn?"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Thuốc uống sau ăn nhé"


@pytest.mark.asyncio
async def test_list_chat_conversations_patient_scoped(client):
    patient_1_id = await _create_patient(PATIENT_1_PHONE)
    patient_2_id = await _create_patient(PATIENT_2_PHONE)

    # Seed conversations directly for patient 1 and patient 2
    async with AsyncSessionLocal() as db:
        async with db.begin():
            c1 = ChatConversation(patient_id=patient_1_id, summary="Hỏi về huyết áp")
            c2 = ChatConversation(patient_id=patient_1_id, summary="Hỏi về lịch uống")
            c3 = ChatConversation(patient_id=patient_2_id, summary="Hỏi của patient 2")
            db.add_all([c1, c2, c3])
            await db.flush()

            m1_1 = ChatMessage(conversation_id=c1.id, role="user", content="Huyết áp hôm nay cao")
            m1_2 = ChatMessage(conversation_id=c1.id, role="assistant", content="Bạn nên nghỉ ngơi")
            m2_1 = ChatMessage(conversation_id=c2.id, role="user", content="Lịch uống lúc mấy giờ?")
            m3_1 = ChatMessage(conversation_id=c3.id, role="user", content="Thuốc của bệnh nhân 2")
            db.add_all([m1_1, m1_2, m2_1, m3_1])

    # Patient 1 lists conversations
    headers_1 = _auth_headers(patient_1_id, PATIENT_1_PHONE)
    res_1 = await client.get("/api/v1/chat/conversations", headers=headers_1)
    assert res_1.status_code == 200
    body_1 = res_1.json()["data"]
    assert body_1["total_elements"] == 2
    assert len(body_1["content"]) == 2
    titles = [item["title"] for item in body_1["content"]]
    assert "Hỏi về huyết áp" in titles
    assert "Hỏi về lịch uống" in titles
    # Ensure patient 2 conversation is NOT returned
    assert "Hỏi của patient 2" not in titles

    # Patient 2 lists conversations
    headers_2 = _auth_headers(patient_2_id, PATIENT_2_PHONE)
    res_2 = await client.get("/api/v1/chat/conversations", headers=headers_2)
    assert res_2.status_code == 200
    body_2 = res_2.json()["data"]
    assert body_2["total_elements"] == 1
    assert body_2["content"][0]["title"] == "Hỏi của patient 2"


@pytest.mark.asyncio
async def test_get_conversation_detail_ownership_and_pagination(client):
    patient_1_id = await _create_patient(PATIENT_1_PHONE)
    patient_2_id = await _create_patient(PATIENT_2_PHONE)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            c1 = ChatConversation(patient_id=patient_1_id, summary="Chi tiết hội thoại 1")
            db.add(c1)
            await db.flush()

            base_time = datetime.now(UTC) - timedelta(minutes=30)
            for i in range(5):
                db.add(
                    ChatMessage(
                        conversation_id=c1.id,
                        role="user",
                        content=f"User msg {i}",
                        created_at=base_time + timedelta(minutes=i * 2),
                    )
                )
                db.add(
                    ChatMessage(
                        conversation_id=c1.id,
                        role="assistant",
                        content=f"AI msg {i}",
                        created_at=base_time + timedelta(minutes=i * 2 + 1),
                    )
                )

    headers_1 = _auth_headers(patient_1_id, PATIENT_1_PHONE)
    headers_2 = _auth_headers(patient_2_id, PATIENT_2_PHONE)

    # Patient 2 cannot access Patient 1's conversation
    forbidden_res = await client.get(f"/api/v1/chat/conversations/{c1.id}", headers=headers_2)
    assert forbidden_res.status_code == 403

    # Patient 1 loads with limit = 4
    detail_res = await client.get(f"/api/v1/chat/conversations/{c1.id}?limit=4", headers=headers_1)
    assert detail_res.status_code == 200
    detail = detail_res.json()["data"]
    assert detail["title"] == "Chi tiết hội thoại 1"
    assert len(detail["messages"]) == 4
    assert detail["hasMore"] is True
    assert detail["nextCursor"] is not None

    # Load older messages using before cursor
    cursor = detail["nextCursor"]
    older_res = await client.get(f"/api/v1/chat/conversations/{c1.id}?limit=4&before={cursor}", headers=headers_1)
    assert older_res.status_code == 200
    older_detail = older_res.json()["data"]
    assert len(older_detail["messages"]) == 4


@pytest.mark.asyncio
async def test_chat_cache_and_invalidation(client):
    settings = get_settings()
    settings.cache_enabled = True
    redis = FakeRedis()

    patient_id = await _create_patient(PATIENT_1_PHONE)
    headers = _auth_headers(patient_id, PATIENT_1_PHONE)

    async def _get_redis_client():
        return redis

    with patch("src.core.cache.get_redis_client", new=_get_redis_client):
        # Initial list is empty and gets cached.
        res1 = await client.get("/api/v1/chat/conversations", headers=headers)
        assert res1.status_code == 200
        assert res1.json()["data"]["total_elements"] == 0
        assert redis.set_calls

        # Direct DB writes do not invalidate cache; the second GET proves it is
        # served from Redis, not freshly loaded from Postgres.
        async with AsyncSessionLocal() as db:
            async with db.begin():
                db.add(ChatConversation(patient_id=patient_id, summary="Direct DB conversation"))

        res_cached = await client.get("/api/v1/chat/conversations", headers=headers)
        assert res_cached.status_code == 200
        assert res_cached.json()["data"]["total_elements"] == 0

        mock_agent_result = {
            "messages": [AsyncMock(content="Câu trả lời mới")],
            "intent": "GENERAL_INQUIRY",
        }
        with patch("src.modules.agents.service.agent.ainvoke", new=AsyncMock(return_value=mock_agent_result)):
            post_res = await client.post(
                "/api/v1/chat",
                json={"message": "Câu hỏi đầu tiên"},
                headers=headers,
            )
        assert post_res.status_code == 200
        assert redis.unlink_calls

        res2 = await client.get("/api/v1/chat/conversations", headers=headers)
        assert res2.status_code == 200
        assert res2.json()["data"]["total_elements"] == 2
        titles = {item["title"] for item in res2.json()["data"]["content"]}
        assert titles == {"Câu hỏi đầu tiên", "Direct DB conversation"}
