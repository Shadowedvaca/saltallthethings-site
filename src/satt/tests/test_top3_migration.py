"""Static Alembic chain coverage for the Top 3 privacy migration."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_top3_migration_is_the_single_reversible_head():
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0010"]
    revision = scripts.get_revision("0008")
    assert revision is not None
    assert revision.down_revision == "0007"
    assert revision.module.upgrade is not None
    assert revision.module.downgrade is not None
