"""Static Alembic chain coverage for the Song Bank migration."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_song_migration_is_the_single_reversible_head():
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0009"]
    revision = scripts.get_revision("0007")
    assert revision is not None
    assert revision.down_revision == "0006"
    assert revision.module.upgrade is not None
    assert revision.module.downgrade is not None
