"""Reviewed appearance must survive new-card generation without copying content."""
import copy
import json
import pathlib
import shutil
import unittest

import test_cards


class CardAppearanceTest(unittest.TestCase):
    apply = test_cards.CardsTest.apply
    # Reuse the project's setup helpers without inheriting its entire test suite.
    def setUp(self):
        test_cards.CardsTest.setUp(self)
        candidates = [pathlib.Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
                      pathlib.Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
        binary = next((p for p in candidates if p.is_file()), None)
        self.assertIsNotNone(binary, 'Appearance regression requires an installed real TrueType font')
        self.role_fonts = []
        layers = {}
        for role, size, scale, uniform in [('title', 7.25, {'x': .62, 'y': .71}, {'on': False, 'value': 1.8}),
                                           ('detail', 3.9, {'x': .43, 'y': .47}, {'on': True, 'value': .9})]:
            font = self.root/(role+'.ttf')
            shutil.copyfile(binary, font)
            self.role_fonts.append(font)
            layers[role] = dict(appearance=dict(font_path=str(font), font_size=size,
                font_name='Reviewed family', text_color='#ABCDEF', has_shadow=False,
                shadow_alpha=.23, shadow_smoothing=.17, shadow_distance=9,
                shadow_angle=35, shadow_point={'x': 4.2, 'y': -3.1},
                shadow_thickness_projection_enable=False, shadow_thickness_projection_angle=17,
                shadow_thickness_projection_distance=3.25, border_mode=2,
                background_style=0, background_alpha=.7, background_round_radius=.27,
                background_width=.63, background_height=.21, background_vertical_offset=-.04,
                background_horizontal_offset=.03, background_fill='solid', letter_spacing=.19),
                rich_content_example=dict(text='Old 😀', styles=[dict(range=[0, 6], size=size,
                    font={'path': str(font), 'id': ''}, fill={'render_type': 'solid',
                    'content': {'solid': {'color': [.1, .3, .6]}}}, letter_spacing=.19,
                    shadows=[{'distance': 9, 'angle': 35, 'feather': .17}])]),
                clip_scale=scale, uniform_scale=uniform)
        self.appearance = {'version': 1, 'layers': layers}
        self.appearance_path = self.root/'appearance.json'
        self.save_appearance()
        self.plan['cards'][0].update(title='NEW 😀 TITLE', detail='NEW ROLE')

    def save_appearance(self):
        self.appearance_path.write_text(json.dumps(self.appearance))
        self.plan['card_appearance'] = dict(path=str(self.appearance_path),
            sha256=self.tool.digest(self.appearance_path), review='Reviewed both native lines and independent scales.')

    def stage(self, name='run'):
        return self.tool.stage(self.project, copy.deepcopy(self.plan), self.root/name, None)

    def test_new_cards_preserve_exact_reviewed_appearance_and_independent_scales(self):
        before = [p.read_bytes() for p in self.paths]
        stage = self.stage()
        result = self.tool.read(stage/'draft.json')
        self.assertEqual(result['tracks'][:2], self.original['tracks'])
        self.assertEqual(result['materials']['drafts'], self.original['materials']['drafts'])
        self.assertEqual([p.read_bytes() for p in self.paths], before)
        for role, material, track, text, length in zip(('title', 'detail'), result['materials']['texts'],
                result['tracks'][-2:], ('NEW 😀 TITLE', 'NEW ROLE'), (12, 8)):
            approved = self.appearance['layers'][role]
            for key, value in approved['appearance'].items():
                self.assertEqual(material[key], value, (role, key))
            content = json.loads(material['content'])
            self.assertEqual(content['text'], text)
            expected = copy.deepcopy(approved['rich_content_example']['styles'][0])
            expected['range'] = [0, length]
            self.assertEqual(content['styles'], [expected])
            self.assertEqual(material['base_content'], material['content'])
            segment = track['segments'][0]
            self.assertEqual(segment['clip']['scale'], approved['clip_scale'])
            self.assertEqual(segment['uniform_scale'], approved['uniform_scale'])
            self.assertEqual(segment['target_timerange'], {'start': 8000000, 'duration': 3200000})
            self.assertTrue(segment['common_keyframes'])

    def test_changed_appearance_or_role_font_blocks_apply_without_project_writes(self):
        for kind in ('appearance', 'title', 'detail'):
            with self.subTest(kind=kind):
                stage = self.stage(kind)
                path = self.appearance_path if kind == 'appearance' else self.role_fonts[('title', 'detail').index(kind)]
                old = path.read_bytes()
                path.write_bytes(old+b'changed')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    self.apply(stage)
                self.assertEqual(self.tool.read(self.paths[0]), self.original)
                path.write_bytes(old)

    def test_untrusted_internal_appearance_is_discarded(self):
        self.plan.pop('card_appearance')
        card = self.plan['cards'][0]
        card['_appearance'] = {'title': {'appearance': {'has_shadow': False}}}
        card['_appearance_font'] = str(self.role_fonts[0])
        stage = self.stage()
        result = self.tool.read(stage/'draft.json')
        self.assertTrue(result['materials']['texts'][0]['has_shadow'])
        staged_card = self.tool.read(stage/'plan.json')['cards'][0]
        self.assertNotIn('_appearance', staged_card)
        self.assertNotIn('_appearance_font', staged_card)

    def test_layout_positions_width_and_fade_remain_explicit_overrides(self):
        self.plan['style'] = {'fade_seconds': .2}
        self.plan['cards'][0]['text_layout'] = {'fixed_width': 900, 'line_max_width': .7}
        result = self.tool.read(self.stage()/'draft.json')
        self.assertEqual(result['materials']['texts'][0]['fixed_width'], 900)
        self.assertEqual(result['materials']['texts'][0]['line_max_width'], .7)
        self.assertEqual(result['tracks'][-2]['segments'][0]['clip']['transform'], {'x': -.52, 'y': -.66})

    def test_conflicting_font_style_scale_or_restyle_is_refused(self):
        mutations = [lambda: self.plan.update(font=str(self.role_fonts[0])),
            lambda: self.plan.update(style={'title_size': 6}),
            lambda: self.plan['cards'][0].update(font=str(self.role_fonts[0])),
            lambda: self.plan['cards'][0].update(style={'theme': 'noir'}),
            lambda: self.plan['cards'][0].update(text_layout={'scale': .6})]
        original = copy.deepcopy(self.plan)
        for index, mutate in enumerate(mutations):
            self.plan = copy.deepcopy(original)
            mutate()
            with self.subTest(plan=self.plan), self.assertRaisesRegex(ValueError, 'card_appearance.*conflict'):
                self.stage('conflict-'+str(index))
        self.plan = original
        with self.assertRaisesRegex(ValueError, 'card_appearance.*conflict'):
            self.tool.stage(self.project, self.plan, self.root/'cli', self.font)
        with self.assertRaisesRegex(ValueError, 'card_appearance.*restyle'):
            self.tool.stage(self.project, self.plan, self.root/'restyle', None, preserve_owned=True)

    def test_literal_infinity_in_reviewed_text_is_valid(self):
        self.appearance['layers']['title']['rich_content_example']['text'] = 'Infinity'
        self.appearance['layers']['title']['rich_content_example']['styles'][0]['range'] = [0, 8]
        self.save_appearance()
        self.assertEqual(json.loads(self.tool.read(self.stage()/'draft.json')['materials']['texts'][0]['content'])['text'],
                         'NEW 😀 TITLE')

    def test_retargeted_font_symlink_blocks_apply(self):
        link = self.root/'linked-font.ttf'
        link.symlink_to(self.role_fonts[0])
        layer = self.appearance['layers']['detail']
        layer['appearance']['font_path'] = str(link)
        layer['rich_content_example']['styles'][0]['font']['path'] = str(link)
        self.save_appearance()
        stage = self.stage()
        self.font.write_bytes(b'\x00\x01\x00\x00different-font')
        link.unlink()
        link.symlink_to(self.font)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.apply(stage)
        self.assertEqual(self.tool.read(self.paths[0]), self.original)

    def test_invalid_or_unreviewed_appearance_is_refused_before_stage_writes(self):
        def changed(path, value):
            obj = self.appearance
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = value
        bad_font = self.root/'invalid-font.ttf'
        bad_font.write_bytes(b'not a font')
        mutations = [lambda: self.plan['card_appearance'].update(review=' '),
            lambda: self.plan['card_appearance'].update(sha256='0'*64),
            lambda: changed(['version'], 2),
            lambda: changed(['layers', 'title', 'appearance', 'id'], 'old-id'),
            lambda: changed(['layers', 'title', 'clip_scale', 'x'], float('nan')),
            lambda: changed(['layers', 'detail', 'uniform_scale', 'value'], 0),
            lambda: changed(['layers', 'title', 'rich_content_example', 'styles'], []),
            lambda: changed(['layers', 'title', 'rich_content_example', 'styles', 0, 'size'], 4),
            lambda: changed(['layers', 'detail', 'rich_content_example', 'styles', 0, 'font', 'path'], str(self.role_fonts[0])),
            lambda: changed(['layers', 'title', 'appearance', 'font_path'], str(self.font)),
            lambda: changed(['version'], True),
            lambda: self.plan['cards'][0].update(text_layout=None),
            lambda: changed(['layers', 'title', 'clip_scale', 'transform'], {'x': 0}),
            lambda: changed(['layers', 'detail', 'uniform_scale', 'on'], 1),
            lambda: changed(['layers', 'title', 'rich_content_example', 'styles', 0, 'range'], [0, 5]),
            lambda: (changed(['layers', 'title', 'appearance', 'font_path'], str(bad_font)),
                     changed(['layers', 'title', 'rich_content_example', 'styles', 0, 'font', 'path'], str(bad_font)))]
        original = copy.deepcopy(self.appearance)
        original_plan = copy.deepcopy(self.plan)
        for index, mutate in enumerate(mutations):
            self.appearance = copy.deepcopy(original)
            self.plan = copy.deepcopy(original_plan)
            self.save_appearance()
            mutate()
            # Mutations to the source are reviewed by hash, but must still validate.
            if index >= 2:
                self.save_appearance()
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.stage('invalid-'+str(index))
            self.assertFalse((self.root/('invalid-'+str(index))).exists())
