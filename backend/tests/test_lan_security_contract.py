"""局域网开放模式的最小安全边界。"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def remote_client() -> TestClient:
    """模拟同一局域网里的另一台设备，不借用本机地址白名单。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create_tables() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, client=("192.168.1.77", 51234)) as client:
        yield client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_remote_health_check_remains_public(remote_client: TestClient) -> None:
    """加入鉴权后也不能把启动器和监控依赖的健康检查锁死。"""
    assert remote_client.get("/health").status_code == 200


@pytest.mark.xfail(
    strict=True,
    reason="known gap: LAN clients can read saves without an access token",
)
def test_remote_save_list_requires_authentication(remote_client: TestClient) -> None:
    response = remote_client.get("/api/saves")
    assert response.status_code in {401, 403}


@pytest.mark.xfail(
    strict=True,
    reason="known gap: cost-bearing LLM endpoints have no LAN authentication",
)
def test_remote_chat_is_authenticated_before_body_validation(
    remote_client: TestClient,
) -> None:
    # 空 body 避免真的调用模型；安全层应在 Pydantic 校验和付费调用之前拒绝。
    response = remote_client.post("/api/chat", json={})
    assert response.status_code in {401, 403}
