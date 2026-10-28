"""现有 SQLite 存档升级时的最小 schema 迁移测试。"""
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import _add_missing_columns  # noqa: E402


def test_legacy_belief_table_gets_update_turn_and_backfill() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE npc_beliefs (
                id INTEGER PRIMARY KEY,
                session_id VARCHAR(40) NOT NULL,
                npc_name VARCHAR(80) NOT NULL,
                statement TEXT NOT NULL,
                learned_turn INTEGER NOT NULL DEFAULT 0
            )
        """))
        conn.execute(text("""
            INSERT INTO npc_beliefs
                (id, session_id, npc_name, statement, learned_turn)
            VALUES (1, 'save-1', '老板', '钥匙在柜台下', 7)
        """))

        _add_missing_columns(conn)

        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(npc_beliefs)"))}
        updated_turn = conn.scalar(text(
            "SELECT updated_turn FROM npc_beliefs WHERE id = 1"
        ))
        indexes = {row[1] for row in conn.execute(text("PRAGMA index_list(npc_beliefs)"))}

    engine.dispose()
    assert "updated_turn" in columns
    assert updated_turn == 7
    assert "ix_belief_session_turn" in indexes
