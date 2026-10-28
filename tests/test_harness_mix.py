import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from capcut_harness.timeline import inspect_audio
from capcut_harness.mix import render_mix


def wav(path, data, rate=48000):
    data = np.asarray(data)
    if data.ndim == 1:
        data = np.column_stack((data, data))
    with wave.open(str(path), 'wb') as f:
        f.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        f.writeframes((np.clip(data, -1, 1)*32767).astype('<i2').tobytes())


def segment(ident, material, start=0, duration=1000000, source_start=0, volume=1, refs=None):
    return dict(id=ident, material_id=material, volume=volume, visible=True,
                source_timerange=dict(start=source_start, duration=duration),
                target_timerange=dict(start=start, duration=duration), extra_material_refs=refs or [])


def draft(materials, tracks, duration=2000000):
    return dict(id='test-film', version=360000, fps=30, duration=duration, materials=materials, tracks=tracks)


def save_project(path, data):
    path.mkdir(exist_ok=True)
    (path/'draft_info.json').write_text(json.dumps(data))
    return path


class MixTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.project = self.root/'film'; self.project.mkdir()
        wav(self.project/'voice.wav', np.full(96000, .1))

    def simple(self):
        return draft({'audios': [dict(id='a', path='voice.wav')]},
                     [dict(id='audio', type='audio', segments=[segment('s', 'a', duration=2000000)])])

    def test_near_full_scale_source_is_reported_before_timeline_gain(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=root/'project';project.mkdir()
            wav(project/'hot.wav',np.clip(np.sin(np.arange(48000)*2*np.pi*500/48000)*2,-1,1))
            save_project(project,draft({'audios':[dict(id='hot',path='hot.wav')]},[dict(id='t',type='audio',segments=[segment('s','hot',volume=.05)])],duration=1000000))
            result=render_mix(inspect_audio(project),root/'mix')
            self.assertGreater(result['source_quality'][0]['near_full_scale_samples'],1000)
            audio=np.memmap(result['raw_path'],dtype='<f4',mode='r')
            self.assertLess(float(np.max(np.abs(audio))),.051)

    def test_overlap_sums_without_normalization_and_duration_is_exact(self):
        d = self.simple(); d['tracks'][0]['segments'].append(segment('second', 'a', start=500000, duration=1000000))
        save_project(self.project, d); info = inspect_audio(self.project)
        out = self.root/'mix'; report = render_mix(info, out, lambda *a: None, lambda: False)
        data = np.memmap(out/'mix.f32', dtype='<f4', mode='r').reshape(-1, 2)
        self.assertEqual(len(data), 96000); self.assertEqual(report['samples'], 96000)
        self.assertAlmostEqual(float(data[1000, 0]), .1, places=3)
        self.assertAlmostEqual(float(data[30000, 0]), .2, places=3)

    def test_separated_video_does_not_double_detached_sound(self):
        d = self.simple(); d['materials']['videos'] = [dict(id='v', path='voice.wav', has_audio=True, has_sound_separated=True)]
        d['tracks'].insert(0, dict(id='video', type='video', segments=[segment('video-s', 'v', duration=2000000)]))
        save_project(self.project, d); info = inspect_audio(self.project)
        self.assertEqual([s['id'] for s in info['sources']], ['s'])
        self.assertEqual(info['separated_video_count'], 1)

    def test_nested_trim_speed_gain_and_ancestor_fade(self):
        inner = self.simple(); inner['materials']['audio_fades'] = [dict(id='fade', fade_type=0, fade_in_duration=1000000, fade_out_duration=0)]
        child = inner['tracks'][0]['segments'][0]; child['extra_material_refs'] = ['fade']; child['volume'] = .5
        outer = segment('compound-s', 'c', start=500000, duration=1000000, source_start=500000, volume=.5)
        outer['source_timerange']['duration'] = 2000000
        d = draft({'drafts': [dict(id='c', draft=inner)]}, [dict(id='main', type='video', segments=[outer])])
        save_project(self.project, d); info = inspect_audio(self.project)
        self.assertFalse(info['issues']); self.assertEqual(len(info['sources']), 1)
        self.assertEqual(info['sources'][0]['speed'], 2)
        out=self.root/'nested';render_mix(info,out,lambda *a:None,lambda:False)
        audio=np.memmap(out/'mix.f32',dtype='<f4',mode='r').reshape(-1,2)
        self.assertLess(abs(float(audio[100,0])), 1e-7)
        self.assertAlmostEqual(float(audio[24000+6000,0]), .01875, delta=.001)
        self.assertLess(abs(float(audio[65000,0])),1e-7)

    def test_missing_media_and_unknown_audio_semantics_are_explicit(self):
        d=self.simple();d['materials']['audios'][0]['path']='missing.wav'
        save_project(self.project,d);info=inspect_audio(self.project)
        self.assertIn('s', str(info['issues']));self.assertIn('Missing',str(info['issues']))
        with self.assertRaisesRegex(ValueError,'Missing'):
            render_mix(info,self.root/'bad',lambda *a:None,lambda:False)
        d=self.simple(); d['tracks'][0]['segments'][0]['common_keyframes']=[dict(property_type='KFTypeVolume')]
        save_project(self.project,d);self.assertIn('keyframe',str(inspect_audio(self.project)['issues']))
        d=self.simple();d['materials']['audio_effects']=[dict(id='fx',type='robot')]
        d['tracks'][0]['segments'][0]['extra_material_refs']=['fx']
        save_project(self.project,d);self.assertIn('audio_effects',str(inspect_audio(self.project)['issues']))

    def test_silent_media_is_not_an_error_and_cancel_stops_decode(self):
        d=self.simple();d['tracks'][0]['segments'][0]['volume']=0
        save_project(self.project,d);info=inspect_audio(self.project)
        self.assertEqual(info['sources'],[])
        info=inspect_audio(save_project(self.project,self.simple()))
        with self.assertRaisesRegex(InterruptedError,'cancel'):
            render_mix(info,self.root/'cancel',lambda *a:None,lambda:True)


if __name__=='__main__':unittest.main()
