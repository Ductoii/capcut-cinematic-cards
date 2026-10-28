#!/usr/bin/env python3
"""Pinned local harness installer. Python 3.10–3.13; no global pip changes."""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import time
import stat
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile

REPO='Ductoii/capcut-cinematic-cards'
VERSION='v0.3.0'
NAMES=('capcut-harness',)
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
              'skills/capcut-harness/SKILL.md','skills/capcut-harness/scripts/cards.py','capcut_harness/mcp.py']
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
        # The old separately discoverable cards skill is folded into the primary
        # harness skill. Preserve it outside discovery only when we own it.
        old=skills_root/'capcut-cinematic-cards'
        if old.is_dir() and not old.is_symlink():
            try:owned=json.loads((old/'.installation.json').read_text()).get('repo')==REPO
            except (ValueError,OSError):owned=False
            if owned:
                saved=backup/'capcut-cinematic-cards';old.rename(saved);changes.append((old,saved))
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


def upgrade_service(root):
    """Stop only an idle old service demonstrably owned by this installation."""
    state=Path.home()/'.local/share/capcut-harness'
    record=state/'server.json';owner=state/'service.lock'
    if not owner.exists() or not record.exists():return
    info=json.loads(record.read_text());pid=int(owner.read_text())
    try:os.kill(pid,0)
    except ProcessLookupError:return
    if info.get('pid')!=pid:raise ValueError('Service ownership changed; preserving the running process')
    from urllib.parse import urlsplit
    url=info['url'].rstrip('/');parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path:raise ValueError('Invalid managed service URL')
    with urllib.request.urlopen(url+'/api/bootstrap',timeout=10) as r:boot=json.load(r)
    if boot.get('version')==VERSION.lstrip('v'):return
    request=urllib.request.Request(url+'/api/jobs',headers={'X-Harness-Token':boot['token']})
    with urllib.request.urlopen(request,timeout=10) as r:jobs=json.load(r)
    if any(j['state'] in ('queued','running','applying','restoring') for j in jobs):
        raise ValueError('Existing harness job is busy; let it finish, then rerun this installer')
    if os.name!='posix':raise ValueError('Close the previous managed harness service before upgrading')
    command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()
    if str(Path(root).expanduser().resolve()/'versions') not in command or '-m capcut_harness' not in command:
        raise ValueError('Running process is not this managed harness; preserving it')
    if int(owner.read_text())!=pid:raise ValueError('Service ownership changed')
    os.kill(pid,signal.SIGINT)
    for _ in range(100):
        if not owner.exists():return
        time.sleep(.1)
    raise ValueError('Old harness is still shutting down safely; rerun installer after it finishes')


def register_plugin(result,root):
    """Use native CLI registration; never edit unrelated user configuration."""
    root=Path(root).expanduser().resolve();release=Path(result['release']);app=release/'app'
    python=release/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    codex=shutil.which('codex')
    if not codex:
        candidate=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
        if candidate.is_file():codex=str(candidate)
    if not codex:raise ValueError('Codex CLI unavailable; open/install the Codex desktop app before plugin registration')
    marketplace=root/'marketplace';managed(marketplace)
    marketplace.mkdir(parents=True,exist_ok=True)
    (marketplace/'.installation.json').write_text(json.dumps(dict(repo=REPO,version=VERSION)))
    plugin=marketplace/'plugins/capcut-harness'
    if plugin.exists():
        saved=root/'backups'/('plugin-'+uuid.uuid4().hex);saved.parent.mkdir(parents=True,exist_ok=True);plugin.rename(saved)
    (plugin/'.codex-plugin').mkdir(parents=True)
    shutil.copytree(app/'skills/capcut-harness',plugin/'skills/capcut-harness')
    descriptor=dict(name='capcut-harness',version=VERSION[1:],description='Local CapCut panel in the current chat, cinematic cards and source-aware film dialogue.',skills='./skills/',mcpServers='./.mcp.json')
    (plugin/'.codex-plugin/plugin.json').write_text(json.dumps(descriptor,indent=2))
    transport=dict(command=str(python),args=['-m','capcut_harness.mcp'],cwd=str(app),env=dict(PYTHONPATH=str(app)))
    (plugin/'.mcp.json').write_text(json.dumps(dict(mcpServers={'capcut-harness':transport}),indent=2))
    catalog=marketplace/'.agents/plugins/marketplace.json';catalog.parent.mkdir(parents=True,exist_ok=True)
    catalog.write_text(json.dumps(dict(name='capcut-harness-local',plugins=[dict(name='capcut-harness',source=dict(source='local',path='./plugins/capcut-harness'))]),indent=2))
    for args in ([codex,'plugin','marketplace','add',str(marketplace),'--json'],[codex,'plugin','add','capcut-harness@capcut-harness-local','--json']):
        outcome=subprocess.run(args,capture_output=True,text=True,timeout=45)
        if outcome.returncode:raise ValueError('Codex plugin registration failed: '+outcome.stderr[-1500:])
    marker=root/'.installation.json';record=json.loads(marker.read_text());record['plugin']=dict(name='capcut-harness@capcut-harness-local',marketplace=str(marketplace),version=VERSION)
    marker.write_text(json.dumps(record,indent=2));return record['plugin']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.local/share/capcut-harness-tool')
    parser.add_argument('--skills-dir',type=Path,default=Path.home()/'.agents/skills')
    parser.add_argument('--bin-dir',type=Path,default=Path.home()/'.local/bin')
    parser.add_argument('--archive',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--register-only',action='store_true',help='Repair the managed local Codex plugin registration')
    args=parser.parse_args()
    if args.register_only:
        root=args.root.expanduser();record=json.loads((root/'.installation.json').read_text())
        print(json.dumps(register_plugin(record,root),ensure_ascii=False,indent=2));return
    if args.archive:raw=args.archive.read_bytes()
    else:
        request=urllib.request.Request(f'https://codeload.github.com/{REPO}/zip/refs/tags/{VERSION}',headers={'User-Agent':'capcut-harness-installer'})
        with urllib.request.urlopen(request,timeout=60) as response:raw=response.read(MAX_ARCHIVE+1)
    result=install(raw,args.root,args.skills_dir,args.bin_dir)
    upgrade_service(args.root)
    result['plugin']=register_plugin(result,args.root)
    print(json.dumps(result,ensure_ascii=False,indent=2));print('Installed. In a fresh local Codex chat: $capcut-harness. The panel sends requests to that same chat.')


if __name__=='__main__':
    try:main()
    except Exception as exc:print('Installation failed: '+str(exc),file=sys.stderr);raise SystemExit(1)
