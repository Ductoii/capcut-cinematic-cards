import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from capcut_harness.audio import analyze,render,parameters
from capcut_harness.loudness import measure
from capcut_harness.speech import detect
from test_harness_mix import wav


def spoken_fixture(root):
    text='The old station is quiet tonight. Please leave the window open, and tell me when the last train arrives.'
    if shutil.which('say'):
        source=root/'speech.aiff';subprocess.run(['say','-v','Samantha','-r','155','-o',str(source),text],check=True)
    elif shutil.which('espeak'):
        source=root/'speech.wav';subprocess.run(['espeak','-s','155','-w',str(source),text],check=True)
    else:raise unittest.SkipTest('Real speech integration requires macOS say or espeak')
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(source),'-ac','1','-ar','48000','-f','f32le','-'])
    voice=np.frombuffer(raw,dtype='<f4');voice=voice/(max(abs(voice)) or 1)*.5
    gap=np.zeros(48000)
    all_audio=np.concatenate((gap,voice*.45,gap,voice*1.2,gap,voice*.3,gap))
    target=root/'speech-levels.wav';wav(target,all_audio)
    return target,len(all_audio)


class AudioTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_real_speech_levels_converge_and_output_peak_duration_are_measured(self):
        source,samples=spoken_fixture(self.root)
        a=analyze(source,self.root/'analysis',{},lambda *a:None,lambda:False)
        self.assertGreaterEqual(len(a['intervals']),3)
        report=render(a,self.root/'render',{},[],lambda *a:None,lambda:False)
        self.assertEqual(report['samples'],samples)
        self.assertLess(report['after']['spread_lu'],report['before']['spread_lu']*.6)
        self.assertLessEqual(report['true_peak_dbtp'],-1.4)
        self.assertTrue(all(abs(r['gain_db'])<=12 for r in report['intervals']))
        self.assertEqual([r['id'] for r in report['intervals']],[r['id'] for r in a['intervals']])
        self.assertTrue(Path(report['master']).is_file())
        self.assertTrue(Path(report['before_preview']).is_file())
        self.assertTrue(Path(report['after_preview']).is_file())
        output=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',report['master'],'-f','f32le','-']),dtype='<f4')
        self.assertEqual(len(output),samples*2)
        self.assertLess(np.max(np.abs(output[:24000])),1e-6)

    def test_excluded_regions_and_parameters_are_validated(self):
        with self.assertRaisesRegex(ValueError,'target'):parameters({'target_lufs':-100})
        with self.assertRaisesRegex(ValueError,'Unknown'):parameters({'mystery':1})
        source,samples=spoken_fixture(self.root)
        a=analyze(source,self.root/'a',{},lambda *a:None,lambda:False)
        with self.assertRaisesRegex(ValueError,'interval'):
            render(a,self.root/'bad',{},['not-an-interval'],lambda *a:None,lambda:False)
        with self.assertRaisesRegex(InterruptedError,'cancel'):
            render(a,self.root/'cancel',{},[],lambda *a:None,lambda:True)

    def test_no_speech_does_not_invent_gain_or_amplify_silence(self):
        path=self.root/'silence.wav';wav(path,np.zeros(96000))
        a=analyze(path,self.root/'a',{},lambda *a:None,lambda:False)
        self.assertEqual(a['intervals'],[])
        with self.assertRaisesRegex(ValueError,'speech'):
            render(a,self.root/'render',{},[],lambda *a:None,lambda:False)

    def test_short_and_clipped_signals_are_finite_and_changes_invalidate_analysis(self):
        p=self.root/'clipped.wav';wav(p,np.tile([.99,-.99],24000))
        m=measure(p,0,.1)
        self.assertTrue(np.isfinite(m['true_peak_dbtp']))
        source,_=spoken_fixture(self.root);a=analyze(source,self.root/'a',{},lambda *a:None,lambda:False)
        source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            render(a,self.root/'render',{},[],lambda *a:None,lambda:False)

    def test_loudness_window_does_not_read_louder_speech_after_its_end(self):
        signal=np.sin(np.arange(48000)*2*np.pi*500/48000)*.03
        wav(self.root/'alone.wav',signal[:24000])
        wav(self.root/'tail.wav',np.concatenate([signal[:24000],signal*20,signal*20,signal*20]))
        bounded=measure(self.root/'tail.wav',0,.5)
        isolated=measure(self.root/'alone.wav')
        self.assertAlmostEqual(bounded['lufs'],isolated['lufs'],delta=.1)


if __name__=='__main__':unittest.main()
