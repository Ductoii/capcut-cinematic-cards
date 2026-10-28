import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('harness_installer',ROOT/'install-harness.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


def archive(extra=None):
    files={'capcut_harness/__main__.py':'import json;print(json.dumps({"launch":"ok"}))',
           'capcut_harness/__init__.py':'__version__="0.2.0"',
           'capcut_harness/assets/silero_vad.onnx':'test model',
           'capcut_harness/web/index.html':'<!doctype html>',
           'requirements.txt':'',
           'skills/capcut-harness/SKILL.md':'---\nname: capcut-harness\n---',
           'skills/capcut-cinematic-cards/SKILL.md':'cards',
           'skills/capcut-cinematic-cards/scripts/cards.py':'# cards'}
    files.update(extra or {});buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        for name,content in files.items():z.writestr('capcut-cinematic-cards-0.2.0/'+name,content)
    return buffer.getvalue()


def fake_environment(release):
    # Test installer switching without downloading dependencies; real isolated install is separate.
    return Path(sys.executable)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.root=self.base/'tool';self.skills=self.base/'skills';self.bin=self.base/'bin'

    def install(self,raw=None):return installer.install(raw or archive(),self.root,self.skills,self.bin,prepare=fake_environment)

    def test_install_launch_repeat_backup_and_unmanaged_preservation(self):
        result=self.install();launcher=Path(result['launcher'])
        self.assertIn(repr(sys.executable),launcher.read_text(), 'Keep the venv interpreter path; resolving its symlink loses isolation')
        run=subprocess.run([sys.executable,str(launcher),'--help'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(run.stdout),{'launch':'ok'})
        first=result['release'];result2=self.install()
        self.assertNotEqual(first,result2['release']);self.assertTrue(Path(first).is_dir())
        self.assertTrue(list((self.root/'backups').iterdir()))
        skill=self.skills/'capcut-harness';(skill/'.installation.json').unlink()
        with self.assertRaisesRegex(ValueError,'unmanaged'):self.install()
        self.assertTrue((skill/'SKILL.md').exists())

    def test_traversal_symlink_and_incomplete_archive_refused(self):
        for name in ['capcut_harness/../../escape','capcut_harness/../escape','capcut_harness/x\\evil']:
            with self.assertRaisesRegex(ValueError,'Unsafe'):self.install(archive({name:'bad'}))
        raw=io.BytesIO(archive())
        with zipfile.ZipFile(raw,'a') as z:
            info=zipfile.ZipInfo('capcut-cinematic-cards-0.2.0/capcut_harness/link');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/etc/passwd')
        with self.assertRaisesRegex(ValueError,'Unsafe'):self.install(raw.getvalue())
        with self.assertRaises(ValueError):self.install(b'badzip')
        self.assertFalse((self.base/'escape').exists())

    def test_dependency_failure_preserves_current_install_and_skill(self):
        first=self.install();original=Path(first['launcher']).read_bytes();skill=(self.skills/'capcut-harness/SKILL.md').read_bytes()
        def fail(release):raise RuntimeError('pip failed')
        with self.assertRaisesRegex(RuntimeError,'pip failed'):
            installer.install(archive(),self.root,self.skills,self.bin,prepare=fail)
        self.assertEqual(Path(first['launcher']).read_bytes(),original)
        self.assertEqual((self.skills/'capcut-harness/SKILL.md').read_bytes(),skill)


if __name__=='__main__':unittest.main()
