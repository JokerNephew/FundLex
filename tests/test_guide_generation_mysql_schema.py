"""Regression for the reserved KEY identifier exposed by real MySQL staging."""
from fundlex.db import Database
from fundlex.guide_generation.store import _SCHEMA


def test_corpus_state_mysql_key_is_quoted_and_bounded():
    statement = next(part for part in _SCHEMA.split(';') if 'CREATE TABLE IF NOT EXISTS gg_corpus_state' in part)
    action, translated = Database('mysql://test:test@localhost/test').prepare(statement)
    assert action == 'run'
    assert '`key` VARCHAR(255) PRIMARY KEY' in translated
    assert "MEDIUMTEXT NOT NULL DEFAULT ('')" in translated
