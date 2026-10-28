"""Regression for the reserved KEY identifier exposed by real MySQL staging."""
from fundlex.db import Database
from fundlex.guide_generation.store import _SCHEMA


def test_corpus_state_mysql_key_is_quoted_and_bounded():
    statement = next(part for part in _SCHEMA.split(';') if 'CREATE TABLE IF NOT EXISTS gg_corpus_state' in part)
    action, translated = Database('mysql://test:test@localhost/test').prepare(statement)
    assert action == 'run'
    assert '`key` VARCHAR(255) PRIMARY KEY' in translated
    assert "MEDIUMTEXT NOT NULL DEFAULT ('')" in translated


def test_corpus_upsert_preserves_creation_and_latest_pointer(tmp_path):
    from fundlex.store import RunStore
    from fundlex.guide_generation.models import ContractVersion
    from fundlex.guide_generation.store import GuideGenerationStore
    store = GuideGenerationStore(RunStore(tmp_path))
    current = ContractVersion('latest', 'fund', 'identity', 'Current', latest_known_version=True)
    store.upsert_contract_version(current)
    with store._connect() as db:
        created = db.execute('SELECT created_at FROM gg_contract_versions WHERE contract_version_id=?', ('latest',)).fetchone()['created_at']
    store.upsert_contract_version(current)
    store.upsert_contract_version(ContractVersion('historical', 'fund', 'identity', 'History'))
    with store._connect() as db:
        assert db.execute('SELECT created_at FROM gg_contract_versions WHERE contract_version_id=?', ('latest',)).fetchone()['created_at'] == created
        assert db.execute('SELECT latest_version_id FROM gg_contracts WHERE contract_id=?', ('fund',)).fetchone()['latest_version_id'] == 'latest'
