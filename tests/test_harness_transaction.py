import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from capcut_harness import transaction as tx
from capcut_harness.timeline import inspect_audio
from capcut_harness.legacy import cards
from test_harness_mix import wav,segment,draft,save_project


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.project=self.root/'film';self.project.mkdir();wav(self.project/'voice.wav',np.full(96000,.1))
        inner=draft({'audios':[dict(id='a',path='voice.wav')]},[dict(id='a-track',type='audio',segments=[segment('voice','a',duration=2000000)])])
        self.original=draft({'drafts':[dict(id='c',draft=inner)],'texts':[dict(id='title',content='Untouched title')]},[
            dict(id='main',type='video',segments=[segment('compound','c',duration=2000000,volume=.8)]),
            dict(id='cards',type='text',name='My cards',segments=[])])
        save_project(self.project,self.original)
        (self.project/'draft_info.json.bak').write_bytes((self.project/'draft_info.json').read_bytes())
        self.master=self.root/'master.wav';wav(self.master,np.full(96000,.06))
        self.rendered=dict(master=str(self.master),master_sha256=cards.digest(self.master),samples=96000,sample_rate=48000,
                           channels=2,duration=2,true_peak_dbtp=-2,file_hashes={str(self.master):cards.digest(self.master)},
                           params=dict(peak_dbtp=-1.5),intervals=[dict(id='speech-1',target_met=True)])
        self.info=inspect_audio(self.project)
        self.before={p.name:p.read_bytes() for p in self.project.glob('*.json*')}

    def stage(self):
        return tx.stage(self.info,self.rendered,self.root/'stage')

    def apply(self,stage):
        with mock.patch.object(cards,'editor_running',return_value=False):return tx.apply(stage)

    def test_apply_adds_one_native_master_mutes_only_root_and_undo_is_exact(self):
        stage=self.stage();result=self.apply(stage);self.assertTrue(result['verified']);self.assertFalse(result['editor_render_verified'])
        d=cards.read(self.project/'draft_info.json')
        self.assertEqual(d['materials']['drafts'],self.original['materials']['drafts'])
        self.assertEqual(d['materials']['texts'],self.original['materials']['texts'])
        self.assertEqual(d['tracks'][1],self.original['tracks'][1]);self.assertEqual(d['tracks'][0]['segments'][0]['volume'],0)
        self.assertEqual(d['tracks'][-1]['segments'][0]['volume'],1)
        self.assertEqual(d['tracks'][-1]['segments'][0]['target_timerange'],dict(start=0,duration=2000000))
        self.assertEqual((self.project/'draft_info.json').read_bytes(),(self.project/'draft_info.json.bak').read_bytes())
        self.assertTrue(tx.verify(stage)['verified']);self.apply(stage)
        with self.assertRaisesRegex(ValueError,'already'):inspect_audio(self.project)
        with mock.patch.object(cards,'editor_running',return_value=False):tx.undo(stage)
        for name,raw in self.before.items():self.assertEqual((self.project/name).read_bytes(),raw)
        self.assertFalse((self.project/tx.STATE).exists())
        self.assertEqual(len(list((self.project/'Resources/HarnessAudio').glob('*.wav'))),1)

    def test_busy_and_tampered_output_or_source_never_write(self):
        stage=self.stage()
        with mock.patch.object(cards,'editor_running',return_value=True):
            with self.assertRaisesRegex(ValueError,'CapCut'):tx.apply(stage)
        self.master.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed|integrity'):self.apply(stage)
        for name,raw in self.before.items():self.assertEqual((self.project/name).read_bytes(),raw)

    def test_stale_project_and_shared_lock_preserve_changes(self):
        stage=self.stage();(self.project/'.capcut-cards.lock').write_text('someone else')
        with self.assertRaisesRegex(ValueError,'lock'):self.apply(stage)
        (self.project/'.capcut-cards.lock').unlink()
        (self.project/'draft_info.json').write_text('{"user":"edit"}')
        with self.assertRaisesRegex(ValueError,'changed'):self.apply(stage)
        self.assertEqual((self.project/'draft_info.json').read_text(),'{"user":"edit"}')

    def test_mid_write_failure_rolls_back_without_touching_foreign_bytes(self):
        stage=self.stage();real=tx.atomic_copy;calls=[]
        def fail(target,source):
            calls.append(str(target))
            if len(calls)==3:raise OSError('simulated disk failure')
            return real(target,source)
        with mock.patch.object(tx,'atomic_copy',side_effect=fail):
            with self.assertRaisesRegex(OSError,'disk'):self.apply(stage)
        for name,raw in self.before.items():self.assertEqual((self.project/name).read_bytes(),raw)
        self.assertFalse((self.project/tx.STATE).exists())

    def test_rollback_keeps_master_referenced_by_foreign_draft(self):
        stage=self.stage();real=tx.atomic_copy;calls=[]
        def fail(target,source):
            calls.append(str(target))
            if len(calls)==3:
                draft=self.project/'draft_info.json'
                draft.write_bytes(draft.read_bytes()+b' ')
                raise OSError('foreign edit during write')
            return real(target,source)
        with mock.patch.object(tx,'atomic_copy',side_effect=fail):
            with self.assertRaisesRegex(OSError,'foreign edit'):self.apply(stage)
        data=cards.read(self.project/'draft_info.json')
        resource=Path(data['materials']['audios'][-1]['path'])
        self.assertTrue(resource.is_file(),'Foreign draft still references the generated master')

    def test_restore_refuses_foreign_edit_and_running_editor(self):
        stage=self.stage();self.apply(stage)
        with mock.patch.object(cards,'editor_running',return_value=True):
            with self.assertRaisesRegex(ValueError,'CapCut'):tx.undo(stage)
        (self.project/'draft_info.json').write_text('{"new":"edit"}')
        with mock.patch.object(cards,'editor_running',return_value=False):
            with self.assertRaisesRegex(ValueError,'changed'):tx.undo(stage)
        self.assertEqual((self.project/'draft_info.json').read_text(),'{"new":"edit"}')

    def test_source_tamper_and_editor_reopening_are_guarded(self):
        stage=self.stage()
        with mock.patch.object(cards,'editor_running',side_effect=[False,False,True,False,False,False]):
            with self.assertRaisesRegex(ValueError,'CapCut'):tx.apply(stage)
        for name,raw in self.before.items():self.assertEqual((self.project/name).read_bytes(),raw)
        (self.project/'voice.wav').write_bytes(b'new recording')
        with self.assertRaisesRegex(ValueError,'Source|source|changed'):self.apply(stage)


if __name__=='__main__':unittest.main()
