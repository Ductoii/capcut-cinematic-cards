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
    def tail_fixture(self, root, audio_duration=1.03):
        source = root/'limited-range-tail.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=navy:s=160x90:r=24:d=1', '-f', 'lavfi', '-i',
                        f'sine=frequency=440:sample_rate=16000:duration={audio_duration}',
                        '-c:v', 'mpeg4', '-pix_fmt', 'yuv420p', '-color_range', 'tv',
                        '-c:a', 'aac', '-y', str(source)], check=True, capture_output=True)
        return source

    def test_subframe_video_audio_tail_has_explicit_available_sample_evidence(self):
        import cards
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); source = self.tail_fixture(root)
            before = cards.digest(source)
            info = {'project': str(root/'project'), 'project_sha256': 'fixture', 'duration': 1.03,
                    'warnings': [], 'sources': [dict(path=str(source), kind='videos', source_type='video',
                                                    start=0, end=1.03, source_start=0, speed=1, volume=1)]}
            result = probe(info, .5, .5, 1, root/'evidence')
            tail = result['frames'][-1]
            self.assertEqual(tail['sample_policy'], 'last_available_video_frame')
            self.assertAlmostEqual(tail['requested_source_time'], 1.029)
            self.assertLess(tail['source_time'], tail['video_duration'])
            self.assertTrue(pathlib.Path(tail['file']).stat().st_size)
            self.assertTrue(result['warnings'])
            self.assertEqual(info['warnings'], [])
            self.assertEqual(cards.digest(source), before)

    def test_boundary_inside_last_frame_does_not_warn_of_unavailable_video(self):
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); source = self.tail_fixture(root)
            info = {'project': str(root/'project'), 'project_sha256': 'fixture', 'duration': 1,
                    'warnings': [], 'sources': [dict(path=str(source), kind='videos', source_type='video',
                                                    start=0, end=1, source_start=0, speed=1, volume=1)]}
            result = probe(info, .5, .5, .5, root/'evidence')
            self.assertEqual(result['frames'][-1]['sample_policy'], 'last_video_frame')
            self.assertFalse(result['warnings'])

    def test_longer_bad_trim_is_rejected_instead_of_silently_freezing(self):
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); source = self.tail_fixture(root)
            info = {'project': str(root/'project'), 'project_sha256': 'fixture', 'duration': 1.2,
                    'warnings': [], 'sources': [dict(path=str(source), kind='videos', source_type='video',
                                                    start=0, end=1.2, source_start=0, speed=1, volume=1)]}
            with self.assertRaisesRegex(ValueError, 'more than one frame'):
                probe(info, .5, .5, 1, root/'evidence')

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
