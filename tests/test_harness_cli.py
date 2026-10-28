import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from capcut_harness.service import Service
from capcut_harness.server import create_server
import unittest
from test_harness_audio import spoken_fixture
from test_harness_mix import draft,segment,save_project

ROOT=Path(__file__).resolve().parents[1]


class CliTest(unittest.TestCase):
    def test_command_waits_for_ready_instead_of_cancelling_queued_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,samples=spoken_fixture(root);p=root/'projects'/'Film';p.mkdir(parents=True)
            save_project(p,draft({'audios':[dict(id='voice',path=str(source))]},[dict(id='t',type='audio',segments=[segment('s','voice',duration=round(samples/48000*1e6))])],duration=round(samples/48000*1e6)))
            result=subprocess.run([sys.executable,'-m','capcut_harness','--state-dir',str(root/'state'),'--project-root',str(p.parent),'command','cân âm thoại Film'],cwd=ROOT,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stderr)
            ticket=json.loads(result.stdout);job=json.loads((root/'state/jobs'/ticket['job_id']/'job.json').read_text())
            self.assertEqual(job['state'],'ready',job)

    def test_command_uses_running_ui_service(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);service=Service(root,[]);server=create_server(service,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                service.store.write(root/'server.json',dict(url=f'http://127.0.0.1:{server.server_address[1]}/',pid=__import__('os').getpid()))
                result=subprocess.run([sys.executable,'-m','capcut_harness','--state-dir',str(root),'command','rm -rf /'],cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertIn('Lệnh chưa hỗ trợ',result.stderr)
                self.assertNotIn('already running',result.stderr)
            finally:server.shutdown();server.server_close();service.close();thread.join()


if __name__=='__main__':unittest.main()
