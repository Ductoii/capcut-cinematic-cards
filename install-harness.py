#!/usr/bin/env python3
"""Pinned local harness installer. Python 3.10–3.13; no global pip changes."""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile

REPO='Ductoii/capcut-cinematic-cards'
VERSION='v0.2.0'
NAMES=('capcut-harness','capcut-cinematic-cards')
LAUNCH_MARKER='# Managed by Ductoii/capcut-cinematic-cards harness installer'
MAX_ARCHIVE=20_000_000


def managed(path, marker='.installation.json'):
    path=Path(path)
    if path.is_symlink():raise ValueError('Existing unmanaged symlink: '+str(path))
    if path.exists():
        try:valid=json.loads((path/marker).read_text()).get('repo')==REPO
        except (OSError,ValueError):valid=False
        if not valid:raise ValueError('Existing unmanaged directory; preserving '+str(path))


def extract(raw, destination):
    if len(raw)>MAX_ARCHIVE:raise ValueError('Release archive too large')
    prefix=f'capcut-cinematic-cards-{VERSION[1:]}/';count=total=0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if not member.filename.startswith(prefix):continue
                name=member.filename[len(prefix):];relative=PurePosixPath(name)
                if relative.parts and relative.parts[0] not in ('capcut_harness','skills','requirements.txt','LICENSE','pyproject.toml'):continue
                if member.is_dir():continue
                count+=1;total+=member.file_size
                if relative.is_absolute() or not relative.parts or '..' in relative.parts or '\\' in name or ':' in name or stat.S_ISLNK(member.external_attr>>16) or total>30_000_000 or count>1000:
                    raise ValueError('Unsafe or oversized release archive')
                target=destination/Path(*relative.parts)
                if target.exists():raise ValueError('Unsafe duplicate archive member')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(member))
    except zipfile.BadZipFile as exc:raise ValueError('Invalid release archive') from exc
    required=['capcut_harness/__main__.py','capcut_harness/assets/silero_vad.onnx','capcut_harness/web/index.html','requirements.txt',
              'skills/capcut-harness/SKILL.md','skills/capcut-cinematic-cards/SKILL.md','skills/capcut-cinematic-cards/scripts/cards.py']
    if not all((destination/name).is_file() for name in required):raise ValueError('Incomplete release archive')


def prepare_environment(release):
    if not (3,10)<=sys.version_info[:2]<(3,14):raise ValueError('Use Python 3.10–3.13 for the pinned audio dependencies')
    missing=[name for name in ('ffmpeg','ffprobe') if not shutil.which(name)]
    if missing:raise ValueError('Missing '+', '.join(missing)+'. Ask local Codex to install FFmpeg, then run this installer again.')
    environment=release/'venv'
    subprocess.run([sys.executable,'-m','venv',str(environment)],check=True)
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(python),'-m','pip','--disable-pip-version-check','--no-input','install','-r',str(release/'app/requirements.txt')],check=True)
    subprocess.run([str(python),'-c',"import numpy, onnxruntime; from pathlib import Path; onnxruntime.InferenceSession(str(Path('capcut_harness/assets/silero_vad.onnx')),providers=['CPUExecutionProvider'])"],cwd=release/'app',check=True)
    subprocess.run([str(python),'-m','capcut_harness','--help'],cwd=release/'app',check=True,stdout=subprocess.DEVNULL)
    return python


def install(raw,root,skills_root,bin_dir,prepare=prepare_environment):
    root=Path(root).expanduser();skills_root=Path(skills_root).expanduser();bin_dir=Path(bin_dir).expanduser()
    managed(root)
    for name in NAMES:managed(skills_root/name)
    launcher=bin_dir/('capcut-harness.py' if os.name=='nt' else 'capcut-harness')
    if launcher.is_symlink() or (launcher.exists() and LAUNCH_MARKER not in launcher.read_text()):raise ValueError('Existing unmanaged launcher; preserving '+str(launcher))
    root.mkdir(parents=True,exist_ok=True,mode=0o700);root=root.resolve();skills_root=skills_root.resolve();bin_dir=bin_dir.resolve();launcher=bin_dir/launcher.name
    marker=root/'.installation.json'
    if not marker.exists():marker.write_text(json.dumps(dict(repo=REPO,version=VERSION)))
    lock=root/'install.lock'
    try:
        with lock.open('x') as f:f.write(str(os.getpid()))
    except FileExistsError as exc:raise ValueError('Another installer holds the install lock') from exc
    release=root/'versions'/(VERSION+'-'+uuid.uuid4().hex)
    changes=[];previous_marker=marker.read_bytes()
    try:
        app=release/'app';app.mkdir(parents=True)
        extract(raw,app);python=Path(prepare(release)).absolute()
        skills_root.mkdir(parents=True,exist_ok=True);bin_dir.mkdir(parents=True,exist_ok=True)
        backup=root/'backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
        for name in NAMES:
            target=skills_root/name;managed(target)
            saved=backup/name
            if target.exists():target.rename(saved)
            changes.append((target,saved if saved.exists() else None))
            shutil.copytree(app/'skills'/name,target)
            (target/'.installation.json').write_text(json.dumps(dict(repo=REPO,version=VERSION,release=str(release))))
        if launcher.is_symlink() or (launcher.exists() and LAUNCH_MARKER not in launcher.read_text()):raise ValueError('Existing unmanaged launcher appeared')
        saved=backup/launcher.name
        if launcher.exists():shutil.copy2(launcher,saved)
        changes.append((launcher,saved if saved.exists() else None))
        code='#!/usr/bin/env python3\n'+LAUNCH_MARKER+'\nimport os, sys\n'
        code+=f'os.chdir({str(app)!r})\n'
        code+=f'os.execve({str(python)!r}, [{str(python)!r}, "-m", "capcut_harness", *sys.argv[1:]], dict(os.environ, PYTHONPATH={str(app)!r}))\n'
        temporary=launcher.with_name(launcher.name+'.'+uuid.uuid4().hex+'.part');temporary.write_text(code);temporary.chmod(0o755);os.replace(temporary,launcher)
        marker.write_text(json.dumps(dict(repo=REPO,version=VERSION,release=str(release),launcher=str(launcher))))
        return dict(version=VERSION,release=str(release),launcher=str(launcher),skills=str(skills_root),backup=str(backup))
    except BaseException:
        for target,saved in reversed(changes):
            if target.is_dir():shutil.rmtree(target)
            elif target.exists():target.unlink()
            if saved is not None:saved.rename(target)
        marker.write_bytes(previous_marker)
        if release.exists():shutil.rmtree(release)
        raise
    finally:lock.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.local/share/capcut-harness-tool')
    parser.add_argument('--skills-dir',type=Path,default=Path.home()/'.agents/skills')
    parser.add_argument('--bin-dir',type=Path,default=Path.home()/'.local/bin')
    args=parser.parse_args()
    request=urllib.request.Request(f'https://codeload.github.com/{REPO}/zip/refs/tags/{VERSION}',headers={'User-Agent':'capcut-harness-installer'})
    with urllib.request.urlopen(request,timeout=60) as response:raw=response.read(MAX_ARCHIVE+1)
    result=install(raw,args.root,args.skills_dir,args.bin_dir)
    print(json.dumps(result,ensure_ascii=False,indent=2));print('Installed. Launch: '+result['launcher']);print('In local Codex: $capcut-harness (restart Codex if the new skill is not listed).')


if __name__=='__main__':
    try:main()
    except Exception as exc:print('Installation failed: '+str(exc),file=sys.stderr);raise SystemExit(1)
