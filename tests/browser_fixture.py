"""Disposable real-audio browser fixture; never imported by production."""
import json
import os
import time
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from capcut_harness.service import Service
from capcut_harness.server import create_server
from capcut_harness.legacy import cards
from test_harness_audio import spoken_fixture
from test_harness_mix import draft,segment,save_project

with tempfile.TemporaryDirectory(prefix='capcut-harness-browser-') as directory:
    root=Path(directory);source,samples=spoken_fixture(root)
    project=root/'projects'/'Test film';project.mkdir(parents=True)
    save_project(project,draft({'audios':[dict(id='voice',path=str(source))]},[
        dict(id='dialogue',type='audio',segments=[segment('voice-segment','voice',duration=round(samples/48000*1e6))])],duration=round(samples/48000*1e6)))
    cards.editor_running=lambda:(root/'busy').exists()
    service=Service(root/'state',[project.parent]);server=create_server(service,0)
    if os.environ.get('READY_FIXTURE'):
        ident=service.command('cân âm thoại Test film')['job_id']
        while service.job(ident)['state'] in ('queued','running'):time.sleep(.05)
    print(json.dumps(dict(url=f'http://127.0.0.1:{server.server_address[1]}',root=str(root),project=str(project))),flush=True)
    try:server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt:pass
    finally:server.server_close();service.close()
