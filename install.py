#!/usr/bin/env python3
"""Install the pinned, standalone Codex skill. Python 3.10+, standard library only."""
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import urllib.request
import uuid
import zipfile

REPO = 'Ductoii/capcut-cinematic-cards'
VERSION = 'v0.1.1'
NAME = 'capcut-cinematic-cards'


def install(raw, root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root/NAME
    marker = target/'.installation.json'
    if target.is_symlink() or (target.exists() and (not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('repo') != REPO)):
        raise ValueError('Existing skill is not managed by this installer; preserving it')
    backup = None
    with tempfile.TemporaryDirectory(prefix='.cards-install-', dir=root) as temp:
        staged = Path(temp)/NAME
        staged.mkdir()
        prefix = f'{NAME}-{VERSION[1:]}/skills/{NAME}/'
        total = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if not member.filename.startswith(prefix):
                    continue
                relative = PurePosixPath(member.filename[len(prefix):])
                if member.is_dir():
                    continue
                mode = member.external_attr >> 16
                total += member.file_size
                if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative) or ':' in str(relative) or stat.S_ISLNK(mode) or total > 5000000:
                    raise ValueError('Unsafe or oversized skill archive')
                dest = staged/Path(*relative.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(member))
        if not (staged/'SKILL.md').is_file() or not (staged/'scripts/cards.py').is_file():
            raise ValueError('Release is missing the skill')
        (staged/'.installation.json').write_text(json.dumps({'repo': REPO, 'version': VERSION}), encoding='utf-8')
        lock = root/f'.{NAME}.install-lock'
        try:
            with lock.open('x') as handle:
                handle.write(str(os.getpid()))
        except FileExistsError as exc:
            raise ValueError('Another installer holds the install lock') from exc
        try:
            # Recheck after acquiring the lock; another install may have finished.
            if target.is_symlink() or (target.exists() and (not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('repo') != REPO)):
                raise ValueError('Existing unmanaged skill appeared; preserving it')
            if target.exists():
                backup = root.parent/'capcut-cards-install-backups'/str(uuid.uuid4())
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(backup))
            try:
                staged.rename(target)
            except BaseException:
                if backup is not None:
                    shutil.move(str(backup), str(target))
                raise
        finally:
            lock.unlink(missing_ok=True)
    return {'installed': str(target), 'version': VERSION, 'previous_install_backup': str(backup) if backup else None}


def main():
    if sys.version_info < (3, 10):
        raise ValueError('Python 3.10+ is required')
    url = f'https://codeload.github.com/{REPO}/zip/refs/tags/{VERSION}'
    request = urllib.request.Request(url, headers={'User-Agent': NAME})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(10000001)
    if len(raw) > 10000000:
        raise ValueError('Release download too large')
    result = install(raw, os.environ.get('CAPCUT_CARDS_SKILLS_DIR', str(Path.home()/'.agents/skills')))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('Installed. In Codex use $capcut-cinematic-cards; restart Codex if it has not discovered the skill yet.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Installation failed: {exc}', file=sys.stderr)
        sys.exit(1)
