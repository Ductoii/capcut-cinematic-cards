import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT/'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def archive(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for path in (ROOT/'skills').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                z.write(path, 'capcut-cinematic-cards-0.1.0/'+path.relative_to(ROOT).as_posix())
        if extra:
            z.writestr(*extra)
    return buffer.getvalue()


class InstallerTest(unittest.TestCase):
    def test_install_twice_keeps_previous_skill_and_does_not_touch_other_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)/'skills'
            root.mkdir(); (root/'other.txt').write_text('mine')
            one = installer.install(archive(), root)
            pathlib.Path(one['installed'], 'local-note.txt').write_text('customization')
            two = installer.install(archive(), root)
            self.assertTrue(pathlib.Path(two['installed'], 'SKILL.md').is_file())
            self.assertEqual(pathlib.Path(two['previous_install_backup'], 'local-note.txt').read_text(), 'customization')
            self.assertEqual((root/'other.txt').read_text(), 'mine')

    def test_rejects_archive_escape_and_preserves_unmanaged_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)/'skills'
            with self.assertRaises(ValueError):
                installer.install(archive(('capcut-cinematic-cards-0.1.0/skills/capcut-cinematic-cards/../../escape', 'bad')), root)
            target = root/'capcut-cinematic-cards'
            target.mkdir(); (target/'SKILL.md').write_text('user skill')
            with self.assertRaisesRegex(ValueError, 'managed'):
                installer.install(archive(), root)
            self.assertEqual((target/'SKILL.md').read_text(), 'user skill')

    def test_rejects_windows_drive_escape_on_every_platform(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                installer.install(archive(('capcut-cinematic-cards-0.1.0/skills/capcut-cinematic-cards/C:/escape', 'bad')), pathlib.Path(temp)/'skills')
