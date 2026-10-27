#!/usr/bin/env python3
"""Scoped production release: prepare/verify first, publish only known V1 files.

Run as root using the project Python. Never prints environment values. Existing
production baselines must match the preserved commits before any replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git(repo, *args):
    return subprocess.check_output(['git', '-c', f'safe.directory={repo}', '-C', str(repo), *args])


def env_file():
    values = {}
    for line in Path('/etc/fundlex-recall.env').read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            parsed = shlex.split(value, comments=True)
            values[key] = parsed[0] if parsed else ''
    values.update(FUNDLEX_GUIDE_CORPUS_DIR='/home/opencode/data/funds_word',
                  FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT='1', FUNDLEX_FRONTEND_VERSION='v1')
    return {**os.environ, **values}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    assert os.geteuid() == 0, 'ROOT_REQUIRED'
    repo, backup, prod = args.repo.resolve(), args.backup.resolve(), Path('/opt/fundlex-recall-first')
    assert str(backup).startswith('/tmp/opencode/v1-three-business-release-'), 'BACKUP_SCOPE_REQUIRED'
    names = [f'frontend/{name}' for name in ('app.js', 'app.css', 'compare.js', 'compare.css', 'compare.html', 'workspace.js', 'guide_generation.js', 'guide_generation.css')]
    names += ['fundlex/api.py', 'fundlex/model.py', 'fundlex/workspace.py', 'pyproject.toml', 'uv.lock']
    for package in ('guide_generation', 'regulatory'):
        names += [str(p.relative_to(repo)) for p in sorted((repo / 'fundlex' / package).glob('*.py'))]
    manifest_file = backup / 'manifest.json'
    if not manifest_file.exists():
        backup.mkdir(mode=0o755, parents=True, exist_ok=False)
        (backup / 'before').mkdir()
        manifest = {'head': git(repo, 'rev-parse', 'HEAD').decode().strip(), 'files': {}}
        for name in names:
            old, new = prod / name, repo / name
            assert new.is_file(), 'CANDIDATE_FILE_MISSING'
            before = sha(old)
            if before:
                base = '87601d3' if name == 'fundlex/api.py' else 'c9b3693'
                expected = git(repo, 'show', f'{base}:{name}')
                assert hashlib.sha256(expected).hexdigest() == before, f'PRODUCTION_BASELINE_CHANGED:{name}'
                target = backup / 'before' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, target)
            manifest['files'][name] = {'before': before, 'after': sha(new)}
        shutil.copy2('/etc/fundlex-recall.env', backup / 'environment.before')
        (backup / 'environment.before').chmod(0o600)
        (backup / 'installed-packages.before.txt').write_bytes(subprocess.check_output([str(prod / '.venv/bin/python'), '-m', 'pip', 'freeze']))
        manifest_file.write_text(json.dumps(manifest, indent=2))
    manifest = json.loads(manifest_file.read_text())
    for name, item in manifest['files'].items():
        assert sha(prod / name) == item['before'], f'PRODUCTION_CONCURRENT_CHANGE:{name}'
        assert sha(repo / name) == item['after'], f'CANDIDATE_CHANGED:{name}'
    stage = backup / 'stage'
    if not stage.exists():
        stage.mkdir(mode=0o755)
        for name in ('fundlex', 'frontend'):
            folder = stage / name
            folder.mkdir()
            for child in (prod / name).iterdir():
                if child.name != '__pycache__':
                    (folder / child.name).symlink_to(child, target_is_directory=child.is_dir())
        for name in ('guides', 'rules', 'references'):
            if (prod / name).exists():
                (stage / name).symlink_to(prod / name, target_is_directory=True)
        for name in manifest['files']:
            target = stage / name
            if target.is_symlink():
                target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, target)
            target.chmod(0o644)
    # Use the actual service identity and production MySQL adapter/schema.
    import pwd
    user = pwd.getpwnam('fundlex')
    def service_identity():
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    code = "from fundlex.api import create_app; a=create_app(); assert hasattr(a.state,'guide_generation'); print('production_identity_mysql_schema_import=ok')"
    environment = env_file()
    environment['PYTHONPATH'] = str(stage)
    result = subprocess.run([str(prod / '.venv/bin/python'), '-c', code], cwd=stage,
                            env=environment, preexec_fn=service_identity, capture_output=True)
    (backup / 'stage-check.txt').write_text('passed\n' if result.returncode == 0 else 'failed\n')
    if result.returncode:
        # Keep traceback diagnostics root-only; credentials are not emitted.
        diagnostic = backup / 'stage-error.private.txt'
        diagnostic.write_bytes(result.stderr)
        diagnostic.chmod(0o600)
        raise RuntimeError('STAGE_IMPORT_FAILED_SEE_ROOT_ONLY_DIAGNOSTIC')
    if not args.publish:
        print(json.dumps({'prepared': True, 'files': len(manifest['files']), 'backup': str(backup)}))
        return
    for name, item in manifest['files'].items():
        assert sha(prod / name) == item['before'], f'PRODUCTION_CONCURRENT_CHANGE:{name}'
        target = prod / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.three-business-new')
        shutil.copyfile(repo / name, temporary)
        temporary.chmod(0o644)
    for name in sorted(manifest['files'], key=lambda name: name == 'fundlex/api.py'):
        target = prod / name
        os.replace(target.with_name(target.name + '.three-business-new'), target)
    for name, item in manifest['files'].items():
        assert sha(prod / name) == item['after'], f'PUBLISH_HASH_MISMATCH:{name}'
    (backup / 'published.json').write_text(json.dumps({'head': manifest['head'], 'files': len(manifest['files'])}))
    print(json.dumps({'published': True, 'files': len(manifest['files']), 'head': manifest['head'], 'backup': str(backup)}))


if __name__ == '__main__':
    main()
