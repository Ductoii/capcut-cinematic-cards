import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/capcut-cinematic-cards/scripts/cards.py'


def load_tool():
    if not SCRIPT.exists():
        raise AssertionError('The portable card tool does not exist yet')
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location('cards', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules['cards'] = module
    spec.loader.exec_module(module)
    return module


class CardsTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.project = self.root / 'Film Việt'
        self.project.mkdir()
        (self.project/'private-voice.wav').write_bytes(b'fixture audio bytes')
        self.font = self.root / 'serif.ttf'
        self.font.write_bytes(b'\x00\x01\x00\x00test-font')
        self.frame = self.root / 'review.jpg'
        self.frame.write_bytes(b'\xff\xd8\xfftest-frame')
        nested = {'id': 'inner', 'duration': 20000000, 'materials': {'audios': [{'id': 'voice', 'path': 'private-voice.wav'}]}, 'tracks': [{'id': 'original-voice', 'type': 'audio', 'segments': [{'id': 'speech', 'material_id': 'voice', 'target_timerange': {'start': 0, 'duration': 20000000}}]}]}
        self.original = {'id': 'main', 'version': 360000, 'duration': 20000000, 'fps': 30., 'canvas_config': {'width': 1920, 'height': 1080, 'ratio': '16:9'}, 'materials': {'drafts': [{'id': 'compound', 'type': 'combination', 'draft': nested}], 'videos': [{'id': 'video', 'path': '', 'material_name': 'My compound'}], 'texts': []}, 'tracks': [{'id': 'main-video', 'type': 'video', 'segments': [{'id': 'keep-me', 'material_id': 'video', 'extra_material_refs': ['compound'], 'source_timerange': {'start': 0, 'duration': 20000000}, 'target_timerange': {'start': 0, 'duration': 20000000}, 'volume': .8}]}, {'id': 'user-text', 'type': 'text', 'segments': []}]}
        self.indexed = self.project / 'Timelines/main'
        self.indexed.mkdir(parents=True)
        (self.project / 'Timelines/project.json').write_text(json.dumps({'main_timeline_id': 'main', 'id': 'project-id'}))
        self.paths = [self.project/'draft_info.json', self.project/'draft_info.json.bak', self.project/'template-2.tmp', self.indexed/'draft_info.json', self.indexed/'draft_info.json.bak', self.indexed/'template-2.tmp']
        for p in self.paths:
            p.write_text(json.dumps(self.original))
        self.plan = {'version': 1, 'project_sha256': self.tool.digest(self.indexed/'draft_info.json'), 'protected_ranges': [{'start': 1, 'end': 5, 'reason': 'important line and reaction'}], 'cards': [{'id': 'morning', 'title': 'THE NEXT MORNING', 'detail': 'THE ATRIUM', 'start': 8, 'duration': 3.2, 'evidence': {'start': 7, 'end': 13, 'frames': [str(self.frame)], 'visual_review': 'Empty floor at lower left; faces are higher and right.', 'dialogue_review': 'Reviewed the audio window: no dialogue during this card.'}}]}

    def stage(self, name='run'):
        return self.tool.stage(self.project, copy.deepcopy(self.plan), self.root/name, self.font)

    def apply(self, stage):
        with mock.patch.object(self.tool, 'editor_running', return_value=False):
            return self.tool.apply(stage)

    def test_overlay_preserves_compound_audio_user_tracks_and_syncs_mirrors(self):
        stage = self.stage()
        self.apply(stage)
        out = json.loads((self.project/'draft_info.json').read_text())
        self.assertEqual(out['tracks'][:2], self.original['tracks'])
        self.assertEqual(out['materials']['drafts'], self.original['materials']['drafts'])
        self.assertEqual(out['duration'], self.original['duration'])
        self.assertEqual(len(out['tracks']), 4)
        self.assertTrue(all(p.read_bytes() == self.paths[0].read_bytes() for p in self.paths))
        self.assertEqual(out['materials']['videos'], self.original['materials']['videos'])
        self.assertTrue(self.tool.verify(stage)['verified'])

    def test_refuses_covering_protected_dialogue(self):
        self.plan['cards'][0]['start'] = 3
        self.plan['cards'][0]['evidence']['start'] = 0
        with self.assertRaisesRegex(ValueError, 'protected'):
            self.stage()

    def test_refuses_unreviewed_or_rushed_cards(self):
        self.plan['cards'][0]['duration'] = 1.5
        with self.assertRaisesRegex(ValueError, 'read'):
            self.stage()
        self.plan['cards'][0]['duration'] = 3.2
        self.plan['cards'][0]['evidence']['frames'] = []
        with self.assertRaisesRegex(ValueError, 'frame'):
            self.stage()

    def test_stale_source_does_not_overwrite_manual_edit(self):
        stage = self.stage()
        self.indexed.joinpath('draft_info.json').write_text('{"manual":"edit"}')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.apply(stage)
        self.assertEqual(self.indexed.joinpath('draft_info.json').read_text(), '{"manual":"edit"}')

    def test_busy_editor_is_not_killed_or_bypassed(self):
        stage = self.stage()
        before = self.paths[0].read_bytes()
        with mock.patch.object(self.tool, 'editor_running', return_value=True):
            with self.assertRaisesRegex(ValueError, 'CapCut'):
                self.tool.apply(stage)
        self.assertEqual(self.paths[0].read_bytes(), before)

    def test_repeat_replaces_only_owned_cards_and_restore_keeps_previous_version(self):
        first = self.stage()
        self.apply(first)
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        second = self.stage('run2')
        self.apply(second)
        out = json.loads(self.paths[0].read_text())
        self.assertEqual(len(out['tracks']), 4)
        with mock.patch.object(self.tool, 'editor_running', return_value=False):
            self.tool.restore(second)
        self.assertTrue(self.tool.verify(first)['verified'])

    def test_guarded_restore_preserves_later_user_edits(self):
        stage = self.stage()
        self.apply(stage)
        self.paths[0].write_text('{"new":"user edit"}')
        with mock.patch.object(self.tool, 'editor_running', return_value=False):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.tool.restore(stage)
        self.assertEqual(self.paths[0].read_text(), '{"new":"user edit"}')

    def test_tampered_staged_file_is_rejected(self):
        stage = self.stage()
        (stage/'draft.json').write_text('{"evil":true}')
        with self.assertRaisesRegex(ValueError, 'changed|integrity'):
            self.apply(stage)

    def test_mismatched_root_mirror_is_rejected(self):
        self.paths[0].write_text('{"stale":true}')
        with self.assertRaisesRegex(ValueError, 'mirror'):
            self.stage()

    def test_path_traversal_and_encrypted_drafts_are_rejected(self):
        (self.project/'Timelines/project.json').write_text(json.dumps({'main_timeline_id': '../../elsewhere'}))
        with self.assertRaisesRegex(ValueError, 'timeline'):
            self.tool.inspect(self.project)
        (self.project/'Timelines/project.json').unlink()
        self.paths[0].write_bytes(b'not json')
        with self.assertRaisesRegex(ValueError, 'JSON|encrypted|Ambiguous'):
            self.tool.inspect(self.project)

    def test_character_intro_requires_identity_and_first_appearance_review(self):
        card = self.plan['cards'][0]
        card.update(kind='character', title='MIRA VALE', detail='Restorer')
        with self.assertRaisesRegex(ValueError, 'identity|appearance'):
            self.stage()
        card['evidence'].update(character_identity='Matched script and reference portrait.', first_appearance='Checked all earlier scenes: this is her first visible appearance.')
        self.plan['style'] = {'theme': 'modern-thriller', 'title_color': '#D3E4EF', 'fade_seconds': .3}
        stage = self.stage()
        data = json.loads((stage/'draft.json').read_text())
        self.assertEqual(data['materials']['texts'][0]['text_color'], '#D3E4EF')
        self.assertEqual(data['tracks'][:2], self.original['tracks'])

    def test_style_rejects_unsupported_effects_and_offscreen_detail(self):
        self.plan['style'] = {'effect': 'giant-glitch'}
        with self.assertRaisesRegex(ValueError, 'style'):
            self.stage()
        self.plan.pop('style')
        self.plan['cards'][0]['y'] = -.8
        with self.assertRaisesRegex(ValueError, 'safe'):
            self.stage()

    def character_card(self):
        card = self.plan['cards'][0]
        card.update(kind='character', title='MIRA VALE', detail='Restorer')
        card['evidence'].update(character_identity='Matched the screenplay and reference.', first_appearance='Reviewed earlier scenes and this entrance.')
        return card

    def test_character_role_defaults_are_readable_and_inside_safe_area(self):
        self.character_card()
        stage = self.stage()
        data = self.tool.read(stage/'draft.json')
        name, role = data['materials']['texts']
        self.assertEqual(name['font_size'], 6.2)
        self.assertEqual(role['font_size'], 3.8)
        self.assertEqual(role['text_color'], '#D4CDBE')
        self.assertAlmostEqual(data['tracks'][-2]['segments'][0]['clip']['transform']['y'], -.64)
        self.assertAlmostEqual(data['tracks'][-1]['segments'][0]['clip']['transform']['y'], -.77)
        self.assertEqual(data['tracks'][:2], self.original['tracks'])

    def test_character_role_omission_requires_a_documented_reason(self):
        card = self.character_card()
        card.pop('detail')
        with self.assertRaisesRegex(ValueError, 'role'):
            self.stage()
        card['evidence']['role_omission_reason'] = 'The user explicitly requested names only.'
        stage = self.stage()
        data = self.tool.read(stage/'draft.json')
        self.assertEqual(len(data['tracks']), 3)

    def test_character_custom_style_and_position_override_defaults(self):
        card = self.character_card()
        card.update(y=-.6, style={'detail_size': 4.1, 'detail_color': '#C8DAE6'})
        self.plan['style'] = {'theme': 'modern-thriller', 'title_size': 5.5}
        stage = self.stage()
        data = self.tool.read(stage/'draft.json')
        self.assertEqual(data['materials']['texts'][0]['font_size'], 5.5)
        self.assertEqual(data['materials']['texts'][1]['font_size'], 4.1)
        self.assertEqual(data['materials']['texts'][1]['text_color'], '#C8DAE6')
        self.assertAlmostEqual(data['tracks'][-1]['segments'][0]['clip']['transform']['y'], -.73)

    def test_evidence_changed_after_staging_blocks_commit(self):
        stage = self.stage()
        self.frame.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'evidence|changed'):
            self.apply(stage)

    def test_source_media_changed_after_review_blocks_commit(self):
        stage = self.stage()
        (self.project/'private-voice.wav').write_bytes(b'new voice')
        with self.assertRaisesRegex(ValueError, 'evidence|changed'):
            self.apply(stage)

    def test_repeated_apply_still_requires_editor_closed(self):
        stage = self.stage()
        self.apply(stage)
        with mock.patch.object(self.tool, 'editor_running', return_value=True):
            with self.assertRaisesRegex(ValueError, 'CapCut'):
                self.tool.apply(stage)

    def test_repeated_apply_rechecks_reviewed_sources(self):
        stage = self.stage()
        self.apply(stage)
        (self.project/'private-voice.wav').write_bytes(b'replaced after first apply')
        with self.assertRaisesRegex(ValueError, 'evidence|changed'):
            self.apply(stage)

    def test_restore_stops_if_editor_opens_before_first_write(self):
        stage = self.stage()
        self.apply(stage)
        with mock.patch.object(self.tool, 'editor_running', side_effect=[False, True]):
            with self.assertRaisesRegex(ValueError, 'CapCut'):
                self.tool.restore(stage)
        self.assertTrue(self.tool.verify(stage)['verified'])

    def test_mid_write_failure_rolls_back_all_owned_writes(self):
        stage = self.stage()
        real = self.tool.atomic
        counter = [0]
        def fail_second(path, raw):
            counter[0] += 1
            if counter[0] == 2:
                raise OSError('synthetic storage error')
            return real(path, raw)
        originals = [p.read_bytes() for p in self.paths]
        with mock.patch.object(self.tool, 'atomic', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'storage'):
                self.apply(stage)
        self.assertEqual([p.read_bytes() for p in self.paths], originals)
        self.assertFalse((self.project/self.tool.STATE).exists())

    def test_legacy_24fps_draft_and_missing_text_collection(self):
        import shutil
        shutil.rmtree(self.project/'Timelines')
        self.original['fps'] = 24
        self.original['materials'].pop('texts')
        for path in self.paths[:3]:
            path.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.paths[0])
        stage = self.stage()
        self.apply(stage)
        self.assertTrue(self.tool.verify(stage)['verified'])


if __name__ == '__main__':
    unittest.main()
