import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/capcut-cinematic-cards/scripts'))

import cards
import styles


def make_sample_draft():
    return {
        'id': 'PRJ-1030',
        'version': 360000,
        'fps': 30.0,
        'duration': 60_000_000,
        'canvas_config': {'width': 1920, 'height': 1080, 'ratio': '16:9'},
        'materials': {
            'videos': [],
            'audios': [],
            'texts': [
                {
                    'id': 'SUB-MAT-1',
                    'type': 'subtitle',
                    'name': 'Mr Veal said hello to Coraline in the dining room today.',
                    'base_content': 'Mr Veal said hello to Coraline in the dining room today.',
                    'content': json.dumps({
                        'text': 'Mr Veal said hello to Coraline in the dining room today.',
                        'styles': [{'range': [0, 56], 'size': 5.0}],
                    }),
                    'recognize_task_id': 'TASK-1',
                    'check_flag': 7,
                },
                {
                    'id': 'SUB-NOISE-1',
                    'type': 'subtitle',
                    'name': 'All right.',
                    'base_content': 'All right.',
                    'content': json.dumps({
                        'text': 'All right.',
                        'styles': [{'range': [0, 10], 'size': 5.0}],
                    }),
                    'recognize_task_id': 'TASK-NOISE',
                    'check_flag': 7,
                },
            ],
            'material_animations': [],
        },
        'tracks': [
            {'id': 'TRACK-VID', 'type': 'video', 'segments': []},
            {
                'id': 'TRACK-SUB',
                'type': 'text',
                'segments': [
                    {
                        'id': 'SEG-SUB-1',
                        'material_id': 'SUB-MAT-1',
                        'target_timerange': {'start': 2_500_000, 'duration': 3_200_000},
                        'source_timerange': {'start': 0, 'duration': 3_200_000},
                        'clip': {'transform': {'x': 0.0, 'y': -0.8}, 'scale': {'x': 1.0, 'y': 1.0}},
                        'uniform_scale': {'on': True, 'value': 1.0},
                    },
                    {
                        'id': 'SEG-NOISE-1',
                        'material_id': 'SUB-NOISE-1',
                        'target_timerange': {'start': 10_000_000, 'duration': 800_000},
                        'source_timerange': {'start': 0, 'duration': 800_000},
                        'clip': {'transform': {'x': 0.0, 'y': -0.8}, 'scale': {'x': 1.0, 'y': 1.0}},
                        'uniform_scale': {'on': True, 'value': 1.0},
                    },
                ],
            },
        ],
    }


class V3ConversationStandardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / '1030'
        self.project.mkdir(parents=True)
        self.draft_data = make_sample_draft()
        (self.project / 'draft_info.json').write_text(json.dumps(self.draft_data), encoding='utf-8')
        patch_dir = self.project / 'attachment/patch'
        patch_dir.mkdir(parents=True)
        (patch_dir / 'mini_draft.json').write_text('{}', encoding='utf-8')
        (patch_dir / 'patch.json').write_text('[]', encoding='utf-8')
        (self.project / 'attachment_action_scene.json').write_text(
            json.dumps({
                'caption_id_info': [
                    {'text_material_id': 'SUB-MAT-1', 'recognize_task_id': 'TASK-1'},
                    {'text_material_id': 'SUB-NOISE-1', 'recognize_task_id': 'TASK-NOISE'},
                ]
            }),
            encoding='utf-8',
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_v3_requires_the_end_by_default_unless_explicitly_disabled(self):
        plan_missing_end = {
            'version': 3,
            'theme': 'southern-copper',
            'cards': [
                {
                    'id': 'c1',
                    'type': 'location',
                    'start_s': 0.5,
                    'end_s': 4.0,
                    'x': -0.50,
                    'y': 0.72,
                    'main': 'HARLAN COUNTY, KENTUCKY',
                    'detail': 'AUTUMN — PRESENT DAY',
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, 'THE END'):
            cards.validate_v3_plan(plan_missing_end, self.draft_data)

        plan_explicit_no_end = dict(plan_missing_end, include_ending=False)
        normalized, theme, fade_in, fade_out = cards.validate_v3_plan(plan_explicit_no_end, self.draft_data)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(theme, 'southern-copper')
        self.assertEqual((fade_in, fade_out), (700000, 500000))

    def test_v3_stage_and_apply_attaches_native_fade_in_out_and_styles_subtitles_in_place(self):
        plan = {
            'version': 3,
            'theme': 'christmas-hearth',
            'include_ending': True,
            'subtitles': {
                'preset': 'yellow-cinema-boxless',
                'text_overrides': {
                    'SEG-SUB-1': 'Mr. Vale said hello to Corinne\nin the dining room today.',
                },
                'remove_segment_ids': ['SEG-NOISE-1'],
            },
            'cards': [
                {
                    'id': 'card_01',
                    'type': 'location',
                    'start_s': 0.5,
                    'end_s': 4.2,
                    'x': -0.52,
                    'y': 0.72,
                    'main': '30 YEARS LATER — CHRISTMAS DAY',
                    'detail': 'THE VALE ESTATE',
                },
                {
                    'id': 'card_end',
                    'type': 'ending',
                    'start_s': 55.0,
                    'end_s': 59.0,
                    'x': 0.0,
                    'y': 0.02,
                    'main': 'THE END',
                    'detail': '',
                },
            ],
        }
        stage_dir = self.root / 'stage-v3'
        cards.stage(self.project, plan, stage_dir, font=None)
        with mock.patch.object(cards, 'editor_running', return_value=False):
            res = cards.apply(stage_dir)
        self.assertTrue(res['verified'])

        updated = json.loads((self.project / 'draft_info.json').read_text(encoding='utf-8'))
        # 1. Native Fade In + Fade Out attached to all card segments, common_keyframes == []
        anims = {a['id']: a for a in updated['materials']['material_animations']}
        self.assertEqual(len(anims), 3)  # card_01 main, card_01 detail, card_end main
        for anim in anims.values():
            self.assertEqual([x['id'] for x in anim['animations']], ['6724916044072227332', '6724919382104871427'])
            self.assertEqual([x['type'] for x in anim['animations']], ['in', 'out'])

        card_tracks = [t for t in updated['tracks'] if t.get('name', '').startswith('Cinematic Cards')]
        self.assertEqual(len(card_tracks), 2)
        for track in card_tracks:
            for seg in track['segments']:
                self.assertEqual(seg['common_keyframes'], [])
                self.assertEqual(len(seg['extra_material_refs']), 1)
                self.assertIn(seg['extra_material_refs'][0], anims)

        # 2. Subtitles styled in-place with zero timing drift, noise removed, base_content == content.text
        sub_track = next(t for t in updated['tracks'] if t['id'] == 'TRACK-SUB')
        self.assertEqual(len(sub_track['segments']), 1)
        sub_seg = sub_track['segments'][0]
        self.assertEqual(sub_seg['target_timerange'], {'start': 2_500_000, 'duration': 3_200_000})
        self.assertEqual(sub_seg['clip']['transform']['y'], -0.78)
        sub_mat = next(m for m in updated['materials']['texts'] if m['id'] == 'SUB-MAT-1')
        self.assertEqual(sub_mat['check_flag'], 15)
        self.assertEqual(sub_mat['text_color'], '#E5CE6E')
        self.assertEqual(sub_mat['base_content'], 'Mr. Vale said hello to Corinne\nin the dining room today.')
        self.assertEqual(json.loads(sub_mat['content'])['text'], sub_mat['base_content'])

        # 3. Delta patches removed & attachment_action_scene.json cleaned
        self.assertFalse((self.project / 'attachment/patch/mini_draft.json').exists())
        self.assertFalse((self.project / 'attachment/patch/patch.json').exists())
        action_scene = json.loads((self.project / 'attachment_action_scene.json').read_text(encoding='utf-8'))
        self.assertEqual(len(action_scene['caption_id_info']), 1)
        self.assertEqual(action_scene['caption_id_info'][0]['text_material_id'], 'SUB-MAT-1')

    def test_default_white_cinematic_boxless_subtitle_preset(self):
        updated, summary = cards.apply_subtitle_preset_in_place(self.draft_data)
        self.assertEqual(summary['preset'], 'white-cinematic-boxless')
        sub_mat = next(m for m in updated['materials']['texts'] if m['id'] == 'SUB-MAT-1')
        self.assertEqual(sub_mat['text_color'], '#FFFDF8')
        self.assertEqual(sub_mat['font_size'], 4.2)
        self.assertEqual(sub_mat['check_flag'], 15)
        self.assertEqual(sub_mat['background_alpha'], 0.0)
        self.assertIn('\n', sub_mat['base_content'])


if __name__ == '__main__':
    unittest.main()
