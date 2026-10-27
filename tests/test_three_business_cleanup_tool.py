import importlib.util
from pathlib import Path
import sqlite3

import pytest


def module():
    path = Path(__file__).resolve().parents[1] / 'tools/verification/cleanup_v1_three_business_e2e.py'
    spec = importlib.util.spec_from_file_location('workspace_cleanup', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def seed(tmp_path, status='completed'):
    tool = module()
    conn = sqlite3.connect(tmp_path / 'db.sqlite')
    conn.executescript('''
      CREATE TABLE users (id TEXT PRIMARY KEY,username TEXT,role TEXT);
      CREATE TABLE gg_runs (id TEXT PRIMARY KEY,owner TEXT,status TEXT);
      CREATE TABLE gg_jobs (id TEXT,run_id TEXT,status TEXT);
      CREATE TABLE gg_artifacts (run_id TEXT,object_key TEXT);
      CREATE TABLE gg_contracts (contract_id TEXT PRIMARY KEY);
      INSERT INTO users VALUES ('mine','e2e-v1ws-0123456789abcdef','member');
      INSERT INTO users VALUES ('other','real-user','member');
      INSERT INTO gg_runs VALUES ('run1','mine','complete');
      INSERT INTO gg_runs VALUES ('run2','other','complete');
      INSERT INTO gg_artifacts VALUES ('run1','guide_generation/run1/guide.docx');
      INSERT INTO gg_contracts VALUES ('shared-public-contract');
    ''')
    conn.execute('INSERT INTO gg_jobs VALUES (?,?,?)', ('job', 'run1', status));conn.commit()
    objects = tmp_path / 'objects';target = objects / 'guide_generation/run1/guide.docx'
    target.parent.mkdir(parents=True);target.write_bytes(b'public-test-product')
    evidence = {'username': 'e2e-v1ws-0123456789abcdef', 'uid': 'mine',
                'task_ids': {'revision': [], 'compare': [], 'generation': ['run1']}}
    return tool, tool.Database(conn), objects, evidence


def test_cleanup_dry_run_execute_and_shared_preservation(tmp_path):
    tool, db, objects, evidence = seed(tmp_path)
    assert not tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects)['executed']
    assert len(db.rows('users', '1=1')) == 2
    result = tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects, execute=True)
    assert result['objects_removed'] == 1
    assert not (objects / 'guide_generation/run1').exists()
    assert len(db.rows('gg_contracts', '1=1')) == 1
    assert len(db.rows('users', '1=1')) == 1
    assert db.rows('gg_runs', '1=1')[0]['id'] == 'run2'
    assert not tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects)['username_present']


def test_cleanup_refuses_active_job_and_wrong_identity(tmp_path):
    tool, db, objects, evidence = seed(tmp_path, status='running')
    with pytest.raises(tool.UnsafeCleanup, match='ACTIVE_JOBS'):
        tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects, execute=True)
    evidence['uid'] = 'other'
    with pytest.raises(tool.UnsafeCleanup, match='UID_EVIDENCE'):
        tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects, execute=True)
    assert len(db.rows('users', '1=1')) == 2


def test_environment_json_is_not_shell_tokenized(tmp_path):
    path = tmp_path / 'service.env'
    path.write_text('FUNDLEX_MODEL_REQUEST_OPTIONS_JSON={"enable_thinking": false}\n')
    assert module().read_env(path)['FUNDLEX_MODEL_REQUEST_OPTIONS_JSON'] == '{"enable_thinking": false}'


def test_cleanup_paused_opt_in_never_allows_a_live_lease(tmp_path):
    tool, db, objects, evidence = seed(tmp_path, status='retry_wait')
    db.conn.execute('ALTER TABLE gg_jobs ADD COLUMN lease_until REAL')
    db.conn.execute("UPDATE gg_runs SET status='paused' WHERE id='run1'")
    db.conn.execute('UPDATE gg_jobs SET lease_until=9999999999');db.conn.commit()
    with pytest.raises(tool.UnsafeCleanup, match='ACTIVE_JOBS'):
        tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects, execute=True, allow_paused=True)
    db.conn.execute('UPDATE gg_jobs SET lease_until=NULL');db.conn.commit()
    result = tool.cleanup(db, username=evidence['username'], evidence=evidence, objects=objects, execute=True, allow_paused=True)
    assert result['executed']
