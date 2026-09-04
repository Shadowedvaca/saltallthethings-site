"""Static Alembic coverage for the episode-number override migration."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_episode_number_override_is_the_single_reversible_head():
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0010"]
    revision = scripts.get_revision("0010")
    assert revision is not None
    assert revision.down_revision == "0009"
    assert revision.module.upgrade is not None
    assert revision.module.downgrade is not None


def test_episode_number_override_migration_is_nullable_and_positive():
    source = (
        REPOSITORY_ROOT
        / "src/satt/migrations/versions/0010_add_episode_number_override.py"
    ).read_text(encoding="utf-8")
    assert 'sa.Column("episode_number_override", sa.Integer(), nullable=True)' in source
    assert "episode_number_override IS NULL OR episode_number_override > 0" in source
    assert 'op.drop_column("show_slots", "episode_number_override"' in source
