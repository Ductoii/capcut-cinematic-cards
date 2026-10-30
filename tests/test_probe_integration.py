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
    def test_slow_cut_samples_remain_inside_continuity_review_tolerance(self):
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); source = root/'slow-cut.mkv'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=white:s=160x90:r=24:d=2', '-f', 'lavfi', '-i',
                            'color=c=black:s=160x90:r=24:d=2', '-filter_complex',
                            '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-c:v', 'ffv1',
                            '-y', str(source)], check=True, capture_output=True)
            info = {'project': str(root/'project'), 'project_sha256': 'fixture', 'duration': 40,
                    'warnings': [], 'sources': [dict(path=str(source), kind='videos', source_type='video',
                                                    start=0, end=40, source_start=0, speed=.1, volume=0)]}
            result = probe(info, 20, 2, 2, root/'evidence')
            cut = next(c['timeline_time'] for c in result['cuts'] if c['kind']=='source-internal')
            self.assertAlmostEqual(cut, 20, places=2)
            before = max((f for f in result['frames'] if f['timeline_time'] < cut), key=lambda f:f['timeline_time'])
            after = min((f for f in result['frames'] if f['timeline_time'] > cut), key=lambda f:f['timeline_time'])
            self.assertLessEqual(cut-before['timeline_time'], .15)
            self.assertLessEqual(after['timeline_time']-cut, .15)
            for frame, expected in [(before, 'white'), (after, 'black')]:
                pixel = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', frame['file'],
                                        '-vf', 'scale=1:1', '-pix_fmt', 'gray', '-frames:v', '1',
                                        '-f', 'rawvideo', '-'], check=True, capture_output=True).stdout[0]
                self.assertTrue(pixel>240 if expected=='white' else pixel<10)

    def test_probe_samples_both_sides_of_internal_cut_after_trim_and_slowdown(self):
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); source = root/'two-shots.mkv'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=white:s=160x90:r=24:d=2', '-f', 'lavfi', '-i',
                            'color=c=black:s=160x90:r=24:d=2', '-filter_complex',
                            '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-c:v', 'ffv1',
                            '-y', str(source)], check=True, capture_output=True)
            info = {'project': str(root/'project'), 'project_sha256': 'fixture', 'duration': 10,
                    'warnings': [], 'sources': [dict(path=str(source), kind='videos', source_type='video',
                                                    start=4, end=10, source_start=1, speed=.5, volume=0)]}
            result = probe(info, 6, 2, 4, root/'evidence')
            internal = [c for c in result.get('cuts', []) if c.get('kind') == 'source-internal']
            self.assertEqual(len(internal), 1)
            self.assertAlmostEqual(internal[0]['timeline_time'], 6, places=2)
            times = [f['timeline_time'] for f in result['frames']]
            self.assertTrue(any(5.90 <= t < 6 for t in times), times)
            self.assertTrue(any(6 < t <= 6.10 for t in times), times)
            before = max((f for f in result['frames'] if f['timeline_time'] < 6), key=lambda f:f['timeline_time'])
            after = min((f for f in result['frames'] if f['timeline_time'] > 6), key=lambda f:f['timeline_time'])
            def luminance(frame):
                pixel = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', frame['file'],
                                        '-vf', 'scale=1:1', '-pix_fmt', 'gray', '-frames:v', '1',
                                        '-f', 'rawvideo', '-'], check=True, capture_output=True).stdout
                return pixel[0]
            self.assertGreater(luminance(before), 240, 'Pre-cut proof must show the old white shot, not seek forward to black')
            self.assertLess(luminance(after), 10)


    def test_snapshot_before_cut_uses_frame_active_at_that_instant_not_future_frame(self):
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);source=root/'active-frame.mkv'
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=white:s=160x90:r=24:d=1',
                            '-f','lavfi','-i','color=c=black:s=160x90:r=24:d=1','-filter_complex',
                            '[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','ffv1','-y',str(source)],
                           check=True,capture_output=True)
            info={'project':str(root/'project'),'project_sha256':'fixture','duration':2,'warnings':[],
                  'sources':[dict(path=str(source),kind='videos',source_type='video',start=0,end=2,source_start=0,speed=1,volume=0)]}
            result=probe(info,1,.01,.1,root/'evidence')
            before=next(f for f in result['frames'] if f['timeline_time']<1)
            pixel=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',before['file'],'-vf','scale=1:1',
                                  '-pix_fmt','gray','-frames:v','1','-f','rawvideo','-'],check=True,capture_output=True).stdout[0]
            self.assertGreater(pixel,240,'At t<1 the old white presentation frame is still active; accurate seek must not jump to the future black shot')
            # Matroska fixture has a millisecond timestamp timebase.
            self.assertAlmostEqual(before['source_time'],23/24,delta=.0005)
            self.assertGreater(before['requested_source_time'],before['source_time'])

    def tail_fixture(self, root, audio_duration=1.03):
        source = root/'limited-range-tail.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=navy:s=160x90:r=24:d=1', '-f', 'lavfi', '-i',
                        f'sine=frequency=440:sample_rate=16000:duration={audio_duration}',
                        '-c:v', 'mpeg4', '-pix_fmt', 'yuv420p', '-color_range', 'tv',
                        '-c:a', 'aac', '-y', str(source)], check=True, capture_output=True)
        return source

    def test_nonzero_container_origin_is_refused_instead_of_guessing_wrong_source_frame(self):
        from media import probe
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);source=root/'offset-origin.mkv'
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=white:s=160x90:r=24:d=1',
                            '-f','lavfi','-i','color=c=black:s=160x90:r=24:d=1','-filter_complex',
                            '[0:v][1:v]concat=n=2:v=1:a=0,setpts=PTS+5/TB[v]','-map','[v]',
                            '-c:v','ffv1','-y',str(source)],check=True,capture_output=True)
            info={'project':str(root/'project'),'project_sha256':'fixture','duration':2,'warnings':[],
                  'sources':[dict(path=str(source),kind='videos',source_type='video',start=0,end=2,source_start=0,speed=1,volume=0)]}
            with self.assertRaisesRegex(ValueError,'timestamp origin'):
                probe(info,1,.01,.1,root/'evidence')
            self.assertFalse(list((root/'evidence').glob('frame-*.jpg')))

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
