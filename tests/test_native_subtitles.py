import copy
import json
import unittest
from unittest import mock

import test_cards


class NativeSubtitleTemplateTest(unittest.TestCase):
    setUp = test_cards.CardsTest.setUp
    stage = test_cards.CardsTest.stage
    apply = test_cards.CardsTest.apply

    def configure(self):
        text = 'good morning everyone happy honey Monday'
        material = dict(id='caption', type='subtitle', name='', recognize_text=text,
                        content=json.dumps({'text': text, 'styles': [{'size': 7, 'range': [0, len(text)]}]}),
                        base_content='old base', font_size=7, check_flag=7, background_style=0,
                        words={'text': ['good', 'morning'], 'start_time': [0, 100], 'end_time': [100, 200]})
        segment = dict(id='cue', material_id='caption', target_timerange={'start': 200000, 'duration': 3400000},
                       clip={'transform': {'x': 0., 'y': -.73}, 'scale': {'x': 1., 'y': 1.}, 'alpha': 1.},
                       extra_material_refs=['unrelated-cue-animation'])
        self.original['materials']['texts'] = [material]
        self.original['tracks'][1]['segments'] = [segment]
        for path in self.paths:
            path.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        source = self.root/'approved-native-subtitle'; source.mkdir()
        data = copy.deepcopy(self.original); data['id'] = 'approved-subtitle'
        template = data['materials']['texts'][0]
        template.update(id='template', font_size=4., check_flag=23, background_style=1,
                        background_color='#000000', background_alpha=.6, font_path=str(self.font),
                        line_max_width=.88, force_apply_line_max_width=False)
        template['content'] = json.dumps({'text': 'Native example', 'styles': [
            {'size': 4., 'range': [0, 14], 'font': {'path': str(self.font), 'id': ''}}]})
        template['base_content'] = template['content']
        data['tracks'][1]['segments'][0].update(material_id='template', id='template-cue')
        (source/'draft_info.json').write_text(json.dumps(data))
        self.plan['subtitle_template'] = dict(source_project=str(source), material_id='template',
            source_project_sha256=self.tool.digest(source/'draft_info.json'),
            review='This native subtitle style is the supplied visual reference.',
            y=-.66, wrap_columns=24)
        return source

    def test_styles_cues_from_native_template_preserving_words_timing_and_media(self):
        self.configure()
        before = copy.deepcopy(self.original)
        stage = self.stage(); self.apply(stage)
        out = self.tool.read(self.paths[0]); m = out['materials']['texts'][0]
        self.assertEqual(m['font_size'], 4.)
        self.assertEqual(m['check_flag'], 23)
        self.assertEqual(m['background_style'], 1)
        self.assertEqual(m['background_alpha'], .6)
        self.assertEqual(m['recognize_text'], before['materials']['texts'][0]['recognize_text'])
        self.assertEqual(m['words'], before['materials']['texts'][0]['words'])
        self.assertEqual(json.loads(m['content'])['text'], 'good morning everyone\nhappy honey Monday')
        self.assertEqual(m['content'], m['base_content'])
        self.assertEqual(out['tracks'][1]['segments'][0]['target_timerange'], {'start': 200000, 'duration': 3400000})
        self.assertEqual(out['tracks'][1]['segments'][0]['clip']['transform'], {'x': 0., 'y': -.66})
        self.assertEqual(out['tracks'][1]['segments'][0]['extra_material_refs'], ['unrelated-cue-animation'])
        self.assertEqual(out['materials']['drafts'], before['materials']['drafts'])
        self.assertEqual(out['tracks'][0], before['tracks'][0])
        with mock.patch.object(self.tool, 'editor_running', return_value=False):
            self.tool.restore(stage)
        self.assertEqual(self.tool.read(self.paths[0]), before)

    def test_changed_subtitle_template_blocks_apply(self):
        source = self.configure(); stage = self.stage()
        (source/'draft_info.json').write_text('{"later":"manual edit"}')
        with self.assertRaisesRegex(ValueError, 'evidence|changed'):
            self.apply(stage)
        self.assertEqual(self.tool.read(self.paths[0]), self.original)

    def test_never_truncates_a_cue_to_fit_two_lines(self):
        self.configure(); self.plan['subtitle_template']['wrap_columns'] = 8
        with self.assertRaisesRegex(ValueError, 'two lines|wrap|fit'):
            self.stage()
        self.assertEqual(self.tool.read(self.paths[0]), self.original)

    def test_reviewed_cue_position_protects_action_without_retiming_other_cues(self):
        self.configure()
        second = copy.deepcopy(self.original['tracks'][1]['segments'][0])
        second.update(id='cue-two', target_timerange={'start': 4000000, 'duration': 2000000})
        self.original['tracks'][1]['segments'].append(second)
        for path in self.paths:
            path.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        self.plan['subtitle_template']['cue_positions'] = [
            {'segment_id': 'cue', 'y': -.3, 'review': 'Viewed whole cue: clear chest band above the teaching hands.'}]
        out = self.tool.read(self.stage()/'draft.json')
        cues = out['tracks'][1]['segments']
        self.assertEqual(cues[0]['clip']['transform'], {'x': 0., 'y': -.3})
        self.assertEqual(cues[1]['clip']['transform'], {'x': 0., 'y': -.66})
        for actual, before in zip(cues, self.original['tracks'][1]['segments']):
            self.assertEqual({k:v for k,v in actual.items() if k!='clip'},
                             {k:v for k,v in before.items() if k!='clip'})
        self.assertEqual(out['materials']['texts'][0]['words'], self.original['materials']['texts'][0]['words'])
        self.assertEqual(self.tool.read(self.paths[0]), self.original)

    def test_unknown_or_duplicate_cue_override_refused(self):
        self.configure()
        self.plan['subtitle_template']['cue_positions'] = [
            {'segment_id': 'missing', 'y': -.3, 'review': 'Reviewed safe position.'}]
        with self.assertRaisesRegex(ValueError, 'Unknown|unknown|missing'):
            self.stage()
        self.plan['subtitle_template']['cue_positions'] = [
            {'segment_id': 'cue', 'y': -.3, 'review': 'Reviewed safe position.'}]*2
        with self.assertRaisesRegex(ValueError, 'Duplicate|duplicate'):
            self.stage()

    def test_ambiguous_source_cue_id_does_not_move_multiple_cues(self):
        self.configure()
        duplicate = copy.deepcopy(self.original['tracks'][1]['segments'][0])
        duplicate['target_timerange'] = {'start': 4000000, 'duration': 2000000}
        self.original['tracks'][1]['segments'].append(duplicate)
        for path in self.paths:
            path.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        self.plan['subtitle_template']['cue_positions'] = [
            {'segment_id': 'cue', 'y': -.3, 'review': 'Reviewed one cue.'}]
        with self.assertRaisesRegex(ValueError, 'Ambiguous|ambiguous|Duplicate|duplicate'):
            self.stage()
        self.assertEqual(self.tool.read(self.paths[0]), self.original)

    def test_one_reviewed_cue_can_wrap_without_rewriting_its_words(self):
        self.configure()
        material = self.original['materials']['texts'][0]
        content = json.loads(material['content'])
        content['text'] = 'they always know who is gentle'
        material['content'] = json.dumps(content)
        for path in self.paths:
            path.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        self.plan['subtitle_template'].update(wrap_columns=34, cue_positions=[
            {'segment_id': 'cue', 'x': .25, 'y': .8, 'wrap_columns': 18,
             'review': 'Whole cue checked in the gap above the handoff and next insert.'}])
        out = self.tool.read(self.stage()/'draft.json')
        text = json.loads(out['materials']['texts'][0]['content'])['text']
        self.assertEqual(text, 'they always know\nwho is gentle')
        self.assertEqual(out['materials']['texts'][0]['words'], material['words'])
        self.assertEqual(out['tracks'][1]['segments'][0]['target_timerange'],
                         self.original['tracks'][1]['segments'][0]['target_timerange'])

    def test_conflicting_wrap_on_shared_material_is_refused_without_project_writes(self):
        self.configure()
        material = self.original['materials']['texts'][0]
        content = json.loads(material['content'])
        content['text'] = 'they always know who is gentle'
        material['content'] = json.dumps(content)
        second = copy.deepcopy(self.original['tracks'][1]['segments'][0])
        second.update(id='cue-two', target_timerange={'start': 4000000, 'duration': 2000000})
        self.original['tracks'][1]['segments'].append(second)
        for path in self.paths:
            path.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        self.plan['subtitle_template'].update(wrap_columns=34, cue_positions=[
            {'segment_id': 'cue', 'wrap_columns': 18, 'y': -.3,
             'review': 'Only this cue needs two lines above the hands.'}])
        with self.assertRaisesRegex(ValueError, 'Shared subtitle material.*wrap'):
            self.stage()
        self.assertEqual(self.tool.read(self.paths[0]), self.original)
