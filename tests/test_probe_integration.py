import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'skills/capcut-cinematic-cards/scripts'))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Optional FFmpeg integration needs ffmpeg and ffprobe')
class ProbeIntegration(unittest.TestCase):
    def test_extracts_real_frames_and_time_aligned_audio_without_source_changes(self):
        import cards
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root/'source.mkv'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=navy:s=320x180:r=24:d=3', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000:duration=3', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-y', str(source)], check=True, capture_output=True)
            before = cards.digest(source)
            info = {'project': str(root/'project'), 'project_sha256': 'fixture', 'duration': 10, 'warnings': [], 'sources': [dict(path=str(source), kind='videos', source_type='video', start=4, end=7, source_start=0, speed=1, volume=1)]}
            result = probe(info, 5, 1, 1, root/'evidence')
            self.assertTrue(result['frames'])
            self.assertEqual(result['audio'][0]['timeline_start'], 4)
            self.assertEqual(result['audio'][0]['timeline_end'], 6)
            self.assertTrue(all(pathlib.Path(row['file']).read_bytes().startswith(b'\xff\xd8\xff') for row in result['frames']))
            audio = pathlib.Path(result['audio'][0]['file'])
            details = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(audio)], capture_output=True, check=True)
            self.assertAlmostEqual(float(json.loads(details.stdout)['format']['duration']), 2, places=2)
            self.assertEqual(cards.digest(source), before)
