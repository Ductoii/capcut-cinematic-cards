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

    def saved_titles(self):
        first = self.stage()
        self.apply(first)
        return self.tool.read(self.paths[0])

    def save_mirrors(self, data):
        for path in self.paths:
            path.write_bytes(self.tool.encoded(data))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')

    def review_saved_ownership(self):
        report = self.tool.inspect(self.project)['ownership']
        self.plan['ownership_review'] = {**report, 'findings': 'Reviewed saved defaults, moved title and user animation against the previous staged draft.'}

    def restyle(self, name='restyle'):
        return self.tool.stage(self.project, copy.deepcopy(self.plan), self.root/name, self.font, preserve_owned=True)

    def test_restyle_preserves_saved_text_position_timing_defaults_and_user_effect(self):
        data = self.saved_titles()
        material = data['materials']['texts'][0]
        material['content'] = material['content'].replace('THE NEXT MORNING', 'USER WORDING')
        material['caption_template_info'] = {'saved_default': True}
        material['name'] = 'User clip label'
        segment = data['tracks'][-2]['segments'][0]
        segment['target_timerange']['start'] = 7500000
        segment['clip']['transform']['x'] = -.4
        segment['extra_material_refs'] = ['user-animation']
        data['materials']['material_animations'] = [{'id': 'user-animation', 'animations': []}]
        # The role remains synced, with its independent position preserved too.
        data['tracks'][-1]['segments'][0]['target_timerange']['start'] = 7500000
        data['tracks'][-1]['segments'][0]['clip']['transform']['x'] = -.3
        self.save_mirrors(data)
        with self.assertRaisesRegex(ValueError, 'ownership_review'):
            self.restyle()
        self.review_saved_ownership()
        self.plan['style'] = {'title_color': '#D3E4EF'}
        before = [p.read_bytes() for p in self.paths]
        stage = self.restyle()
        self.assertEqual([p.read_bytes() for p in self.paths], before)
        self.apply(stage)
        out = self.tool.read(self.paths[0])
        self.assertEqual(out['tracks'], data['tracks'])
        self.assertEqual(out['materials']['material_animations'], data['materials']['material_animations'])
        updated = out['materials']['texts'][0]
        self.assertIn('USER WORDING', updated['content'])
        self.assertEqual(updated['caption_template_info'], {'saved_default': True})
        self.assertEqual(updated['name'], 'User clip label')
        self.assertEqual(updated['text_color'], '#D3E4EF')
        self.assertTrue(self.tool.verify(stage)['verified'])

    def test_restyle_review_is_stale_after_another_saved_edit(self):
        data = self.saved_titles()
        data['materials']['texts'][0]['saved_default'] = True
        self.save_mirrors(data); self.review_saved_ownership()
        data['materials']['texts'][0]['saved_default'] = False
        self.save_mirrors(data)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.restyle()

    def test_restyle_does_not_reclaim_deleted_owned_text(self):
        data = self.saved_titles()
        data['materials']['texts'].pop()
        self.save_mirrors(data); self.review_saved_ownership()
        with self.assertRaisesRegex(ValueError, 'removed'):
            self.restyle()

    def test_restyle_does_not_claim_user_segment_added_inside_owned_track(self):
        data = self.saved_titles()
        data['tracks'][-2]['segments'].append(dict(id='user-segment', material_id='user-material',
                                                   target_timerange={'start': 14000000, 'duration': 3000000}))
        data['materials']['texts'].append(dict(id='user-material', content='keep'))
        self.save_mirrors(data); self.review_saved_ownership()
        with self.assertRaisesRegex(ValueError, 'membership changed'):
            self.restyle()
        self.assertEqual(self.tool.read(self.paths[0]), data)

    def test_restyle_preserves_saved_segment_order(self):
        second = copy.deepcopy(self.plan['cards'][0]); second.update(id='second', start=14)
        second['evidence'].update(start=13, end=19)
        self.plan['cards'].append(second)
        data = self.saved_titles()
        data['tracks'][-2]['segments'].reverse()
        self.save_mirrors(data); self.review_saved_ownership()
        stage = self.restyle(); self.apply(stage)
        self.assertEqual(self.tool.read(self.paths[0])['tracks'], data['tracks'])

    def test_restyle_adds_missing_intro_without_removing_omitted_existing_cards(self):
        data = self.saved_titles()
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        new = copy.deepcopy(self.plan['cards'][0])
        new.update(id='new-intro', title='Mira Vale', detail='Restorer', start=14, duration=3.2, kind='character')
        new['evidence'].update(start=13, end=19, character_identity='Confirmed script identity.', first_appearance='Reviewed earlier scenes.')
        self.plan['cards'] = [new]
        stage = self.restyle()
        self.apply(stage)
        out = self.tool.read(self.paths[0])
        self.assertEqual(len(out['tracks'][-2]['segments']), 2)
        self.assertEqual(out['materials']['texts'][:2], data['materials']['texts'])

    def test_restyle_rejects_new_card_overlapping_an_unlisted_owned_card(self):
        self.saved_titles()
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        self.plan['cards'][0]['id'] = 'new-overlap'
        with self.assertRaisesRegex(ValueError, 'overlaps an existing'):
            self.restyle()

    def test_restyle_preserves_unowned_title_added_to_new_text_collection(self):
        # Initial edits on older drafts may create materials.texts themselves.
        self.original['materials'].pop('texts')
        self.save_mirrors(self.original)
        data = self.saved_titles()
        data['materials']['texts'].append({'id': 'user-added-text', 'content': 'keep exactly'})
        self.save_mirrors(data)
        stage = self.restyle()
        self.apply(stage)
        self.assertIn({'id': 'user-added-text', 'content': 'keep exactly'}, self.tool.read(self.paths[0])['materials']['texts'])
        self.assertTrue(self.tool.verify(stage)['verified'])

    def test_character_cast_review_requires_explicit_coverage_and_supports_pair(self):
        card = self.character_card()
        self.plan['introduce_characters'] = True
        with self.assertRaisesRegex(ValueError, 'every principal'):
            self.stage()
        card['characters'] = ['mira', 'leo']
        self.plan['character_review'] = [dict(id='mira', name='Mira Vale', status='introduced', card_id=card['id']),
                                         dict(id='leo', name='Leo Vale', status='omitted', reason='Identity remains hidden.')]
        with self.assertRaisesRegex(ValueError, 'cast IDs'):
            self.stage()
        self.plan['character_review'][1] = dict(id='leo', name='Leo Vale', status='introduced', card_id=card['id'])
        card['title'] = 'Mira & Leo Vale'
        self.stage()

    def test_character_cast_omissions_need_reasons(self):
        self.character_card()['characters'] = ['mira']
        self.plan['character_review'] = [dict(id='mira', name='Mira Vale', status='introduced', card_id='morning'),
                                         dict(id='leo', name='Leo Vale', status='omitted')]
        with self.assertRaisesRegex(ValueError, 'specific reason'):
            self.stage()

    def test_cast_review_rejects_introducing_the_same_principal_twice(self):
        card = self.character_card(); card['characters'] = ['mira']
        self.plan['character_review'] = [dict(id='mira', name='Mira Vale', status='introduced', card_id='morning')]
        second = copy.deepcopy(card); second.update(id='second-intro', start=14)
        second['evidence'].update(start=13, end=19)
        self.plan['cards'].append(second)
        with self.assertRaisesRegex(ValueError, 'each principal once'):
            self.stage()

    def test_restyle_wording_change_is_explicit_and_removed_cards_stay_protected(self):
        self.saved_titles()
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        self.plan['cards'][0].update(title='CUSTOM HEADING', replace_text=True)
        stage = self.restyle()
        self.apply(stage)
        self.assertIn('CUSTOM HEADING', self.tool.read(self.paths[0])['materials']['texts'][0]['content'])

    def native_fade_fixture(self, data):
        folder = self.root/'existing-fade'; folder.mkdir()
        resource = folder/'config.json'; resource.write_text('{"fixture":true}')
        data['materials']['material_animations'] = [{'id': 'existing-in', 'animations': [dict(type='in', path=str(folder), resource_id='existing-resource')]}]
        segment = data['tracks'][-2]['segments'][0]
        segment['extra_material_refs'] = ['existing-in']
        self.plan['native_fade_in'] = dict(material_id='existing-in', source_segment_id=segment['id'],
                                           review='Reviewed local existing fade-in, not a guessed effect.', files=[str(resource)])
        return resource

    def test_native_fade_reuses_existing_asset_on_both_lines_and_pins_resource(self):
        data = self.saved_titles()
        resource = self.native_fade_fixture(data)
        self.save_mirrors(data); self.review_saved_ownership()
        stage = self.restyle()
        out = self.tool.read(stage/'draft.json')
        self.assertEqual(out['materials']['material_animations'], data['materials']['material_animations'])
        self.assertTrue(all(s['extra_material_refs'] == ['existing-in'] for t in out['tracks'][-2:] for s in t['segments']))
        resource.write_text('changed after review')
        with self.assertRaisesRegex(ValueError, 'evidence|changed'):
            self.apply(stage)

    def test_native_fade_rejects_invented_resource_or_wrong_source_segment(self):
        data = self.saved_titles()
        self.native_fade_fixture(data)
        self.save_mirrors(data); self.review_saved_ownership()
        self.plan['native_fade_in']['source_segment_id'] = 'not-a-real-segment'
        with self.assertRaisesRegex(ValueError, 'source text segment'):
            self.restyle()

    def test_native_fade_never_replaces_a_different_user_animation(self):
        data = self.saved_titles()
        self.native_fade_fixture(data)
        data['materials']['material_animations'].append({'id': 'other-animation', 'animations': []})
        data['tracks'][-1]['segments'][0]['extra_material_refs'] = ['other-animation']
        self.save_mirrors(data); self.review_saved_ownership()
        with self.assertRaisesRegex(ValueError, 'different existing'):
            self.restyle()
        self.assertEqual(self.tool.read(self.paths[0]), data)

    def test_ending_is_native_text_without_timeline_extension(self):
        self.plan['cards'][0].update(kind='ending', title='THE END', detail='', start=16, duration=3.6, layout='center')
        self.plan['cards'][0]['evidence'].update(start=12, end=20)
        stage = self.stage()
        data = self.tool.read(stage/'draft.json')
        self.assertEqual(data['duration'], self.original['duration'])
        self.assertEqual(data['tracks'][:2], self.original['tracks'])
        self.assertEqual(len(data['materials']['videos']), len(self.original['materials']['videos']))


    def paired_plan(self):
        self.plan['protected_ranges'] = [{'start': 7, 'end': 13, 'kind': 'dialogue', 'reason': 'Speech continues'}]
        self.plan['introduce_characters'] = True
        self.plan['character_review'] = []
        self.plan['cards'] = []
        for ident, x, bounds in [('mira', -.5, [-.8, -.6, -.2, -.3]), ('leo', .5, [.2, -.6, .8, -.3])]:
            self.plan['cards'].append(dict(id=ident, kind='character', characters=[ident], title=ident.title(),
                detail='Restorer', start=8, duration=3.2, x=x, y=-.4, simultaneous_group='pair', bounds=bounds,
                exclusion_zones=[[-.85, -.85, .85, -.65]],
                evidence=dict(start=7, end=13, frames=[str(self.frame)], visual_review='Reviewed full two-shot.',
                    dialogue_review='Speech continues; identifiers do not cover captions.',
                    character_identity='Confirmed script identity.', first_appearance='First recognizable view.',
                    layout_review='Full name and role extents checked against subtitles and movement.',
                    identity_association='Label stays beside this person throughout the hold.')))
            self.plan['character_review'].append(dict(id=ident, name=ident.title(), status='introduced', card_id=ident))

    def test_simultaneous_labels_use_separate_tracks_and_preserve_subtitles(self):
        self.paired_plan()
        stage = self.stage(); self.apply(stage)
        data = self.tool.read(self.paths[0])
        self.assertEqual(data['tracks'][:2], self.original['tracks'])
        added = data['tracks'][2:]
        self.assertEqual(len(added), 4)
        self.assertTrue(all(len(t['segments']) == 1 for t in added))
        self.assertTrue(self.tool.verify(stage)['verified'])

    def test_simultaneous_group_requires_distinct_reviewed_noncolliding_labels(self):
        for mutation in ('collision', 'review', 'timing', 'duplicate', 'subtitle', 'third'):
            with self.subTest(mutation=mutation):
                self.paired_plan(); card = self.plan['cards'][1]
                if mutation == 'collision': card['bounds'] = self.plan['cards'][0]['bounds']
                if mutation == 'review': card['evidence'].pop('identity_association')
                if mutation == 'timing': card['start'] += .5
                if mutation == 'duplicate': card['characters'] = ['mira']
                if mutation == 'subtitle': card['exclusion_zones'] = [[.3, -.8, .7, -.4]]
                if mutation == 'third':
                    third = copy.deepcopy(card); third.update(id='accidental', simultaneous_group=None)
                    self.plan['cards'].append(third)
                with self.assertRaises(ValueError): self.stage(mutation)

    def test_restyle_retains_custom_typography_when_only_color_requested(self):
        data = self.saved_titles(); material = data['materials']['texts'][0]
        content = json.loads(material['content']); content['styles'][0].update(size=4.7, letter_spacing=.025)
        content['styles'][0]['font']['path'] = str(self.font)
        material.update(content=json.dumps(content), font_size=4.7, letter_spacing=.025)
        self.save_mirrors(data); self.review_saved_ownership()
        self.plan['style'] = {'title_color': '#ABCDEF'}
        stage = self.tool.stage(self.project, self.plan, self.root/'retain', None, preserve_owned=True)
        self.apply(stage); updated = self.tool.read(self.paths[0])['materials']['texts'][0]
        self.assertEqual(updated['font_size'], 4.7)
        self.assertEqual(updated['letter_spacing'], .025)
        self.assertEqual(json.loads(updated['content'])['styles'][0]['size'], 4.7)
        self.assertEqual(updated['font_path'], material['font_path'])
        self.assertEqual(updated['text_color'], '#ABCDEF')

    def test_per_card_font_multiline_and_explicit_scale_width(self):
        other = self.root/'sans.otf'; other.write_bytes(b'OTTOtest-font')
        card = self.plan['cards'][0]
        card.update(font=str(other), title='THE NEXT\nMORNING', text_layout={'scale': .8, 'line_max_width': .5})
        stage = self.stage(); self.apply(stage); data = self.tool.read(self.paths[0])
        material = data['materials']['texts'][0]; segment = data['tracks'][-2]['segments'][0]
        self.assertEqual(material['font_path'], str(other.resolve()))
        self.assertEqual(json.loads(material['content'])['text'], 'THE NEXT\nMORNING')
        self.assertEqual(material['line_max_width'], .5)
        self.assertTrue(material['force_apply_line_max_width'])
        self.assertEqual(segment['clip']['scale'], {'x': .8, 'y': .8})
        self.assertEqual(segment['uniform_scale']['value'], .8)

    def test_restyle_preserves_short_manual_hold(self):
        data = self.saved_titles()
        for track in data['tracks'][-2:]:
            track['segments'][0]['target_timerange']['duration'] = 2100000
        self.save_mirrors(data); self.review_saved_ownership()
        stage = self.restyle(); self.apply(stage)
        self.assertEqual(self.tool.read(self.paths[0])['tracks'], data['tracks'])

    def test_simultaneous_addition_cannot_overlap_an_omitted_saved_card(self):
        self.saved_titles(); self.paired_plan()
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        with self.assertRaisesRegex(ValueError, 'omitted from the plan'): self.restyle()

    def test_reviewed_bounds_reject_overflow_even_when_anchor_is_safe(self):
        self.plan['cards'][0]['bounds'] = [-1.2, -.8, .2, -.2]
        with self.assertRaisesRegex(ValueError, 'bounds'): self.stage()

    def test_incremental_restyle_syncs_only_owned_content_and_restores(self):
        data = self.saved_titles()
        folder = self.indexed/'attachment/patch'; folder.mkdir(parents=True)
        ss = [{'id': seg['id'], 'material': {'type': 'text', 'content': next(m['content'] for m in data['materials']['texts'] if m['id'] == seg['material_id'])}}
              for track in data['tracks'][-2:] for seg in track['segments']]
        ss.append({'id': 'user-subtitle', 'material': {'content': 'preserve this byte content'}})
        mini = {'mini_draft_data': {'segments': ss, 'header': {'index': 3}}}
        (folder/'mini_draft.json').write_text(json.dumps(mini))
        (folder/'patch.json').write_text('{"patch_data":[]}')
        self.plan.update(project_sha256=self.tool.digest(self.indexed/'draft_info.json'), sync_incremental_snapshot=True,
                         style={'title_color': '#ABCDEF'})
        stage = self.restyle(); self.apply(stage)
        updated = self.tool.read(folder/'mini_draft.json')
        self.assertEqual(updated['mini_draft_data']['segments'][-1], ss[-1])
        self.assertIn('0.670588', updated['mini_draft_data']['segments'][0]['material']['content'])
        with mock.patch.object(self.tool, 'editor_running', return_value=False): self.tool.restore(stage)
        self.assertEqual(self.tool.read(folder/'mini_draft.json'), mini)

    def test_nonempty_incremental_patch_is_never_cleared(self):
        self.saved_titles(); folder = self.indexed/'attachment/patch'; folder.mkdir(parents=True)
        (folder/'mini_draft.json').write_text('{}')
        patch = '{"patch_data":[{"user":"edit"}]}'
        (folder/'patch.json').write_text(patch)
        self.plan.update(project_sha256=self.tool.digest(self.indexed/'draft_info.json'), sync_incremental_snapshot=True)
        with self.assertRaisesRegex(ValueError, 'incremental patch'): self.restyle()
        self.assertEqual((folder/'patch.json').read_text(), patch)

    def test_layout_repair_preserves_populated_subtitles_and_native_animations(self):
        self.original['materials']['texts'] = [dict(id='caption-'+str(i), type='subtitle', content='manual words',
            base_content='manual words', background_alpha=.6) for i in range(288)]
        self.original['tracks'][1]['segments'] = [dict(id='subtitle-segment-'+str(i), material_id='caption-'+str(i)) for i in range(288)]
        self.save_mirrors(self.original)
        data = self.saved_titles()
        self.plan.update(project_sha256=self.tool.digest(self.indexed/'draft_info.json'))
        self.plan['cards'][0].update(bounds=[-.8, -.5, -.2, -.1], text_layout={'scale': .8, 'title_x': -.5, 'title_y': -.2})
        self.plan['cards'][0]['evidence']['layout_review'] = 'Reviewed title/role bounds throughout the hold.'
        stage = self.restyle(); self.apply(stage); updated = self.tool.read(self.paths[0])
        self.assertEqual(updated['tracks'][1], data['tracks'][1])
        self.assertEqual(updated['materials']['texts'][:288], data['materials']['texts'][:288])
        seg = updated['tracks'][-2]['segments'][0]
        self.assertEqual(seg['clip']['transform'], {'x': -.5, 'y': -.2})
        self.assertEqual(seg['clip']['scale']['x'], seg['uniform_scale']['value'])
        self.assertEqual(seg['common_keyframes'], data['tracks'][-2]['segments'][0]['common_keyframes'])


if __name__ == '__main__':
    unittest.main()
