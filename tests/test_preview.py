import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'skills/capcut-cinematic-cards/scripts'))
import preview as tool
from native_text import identity

PILLOW = importlib.util.find_spec('PIL') is not None


@unittest.skipUnless(PILLOW, 'Optional preview needs Pillow')
class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        candidates = [pathlib.Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
                      pathlib.Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
        self.font = next((p for p in candidates if p.is_file()), None)
        self.assertIsNotNone(self.font, 'Integration requires a real installed TrueType font')
        self.entry = dict(**{'class': 'title'}, font_path=str(self.font), font_sha256=tool._hash(self.font),
                          font_size=6, clip_scale={'x': 1, 'y': 1}, letter_spacing=0,
                          observed_font_px=28, tracking_px=0, line_gap_px=5,
                          observation='Fixture explicit observed size; no native conversion')
        self.material = dict(id='title-material', font_path=str(self.font), font_size=6, letter_spacing=0)
        self.segment = dict(clip={'scale': {'x': 1, 'y': 1}})

    def test_explicit_calibration_missing_mismatched_size_scale_spacing_or_font_refused(self):
        calibration = {'entries': [self.entry]}
        self.assertEqual(tool.calibration_entry(calibration, 'title', self.material, self.segment), self.entry)
        for changed in ({'entries': []}, {'entries': [dict(self.entry, font_size=7)]},
                        {'entries': [dict(self.entry, clip_scale={'x': 2, 'y': 2})]},
                        {'entries': [dict(self.entry, letter_spacing=1)]}):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'explicit calibration'):
                tool.calibration_entry(changed, 'title', self.material, self.segment)
        with self.assertRaisesRegex(ValueError, 'font hash mismatch'):
            tool.calibration_entry({'entries': [dict(self.entry, font_sha256='wrong')]}, 'title', self.material, self.segment)

    def test_observed_font_measures_real_ink_and_detects_edge_overflow(self):
        ink, bounds = tool.glyph_sprite('Observed wide glyphs WWW', self.entry)
        self.assertEqual(bounds, ink.getchannel('A').getbbox())
        self.assertGreater(bounds[2]-bounds[0], 250)
        # A harmless-looking declared 20 px rectangle cannot constrain actual ink.
        declared_width, canvas_width, anchor = 20, 480, 460
        self.assertLess(anchor+declared_width/2, canvas_width)
        actual_right = round(anchor-ink.width/2)+bounds[2]
        self.assertGreater(actual_right, canvas_width)

    def test_disabled_native_background_ignores_stored_alpha(self):
        ink, _ = tool.glyph_sprite('Observed ink', self.entry)
        material = dict(background_style=0, background_alpha=1, background_color='#000000')
        sprite = tool._text_appearance(ink, material)
        self.assertEqual(sprite.getchannel('A').tobytes(), ink.getchannel('A').tobytes(),
                         'Disabled native background must not create an opaque rectangle')

    def test_style_one_approximates_backing_and_unknown_enabled_styles_refuse(self):
        from PIL import Image
        ink = Image.new('RGBA', (10, 10), (255, 255, 255, 0)); ink.putpixel((5, 5), (255, 255, 255, 255))
        material = dict(background_style=1, background_alpha=.4, background_color='#000000')
        sprite = tool._text_appearance(ink, material)
        self.assertEqual(sprite.getpixel((0, 0)), (0, 0, 0, 102))
        self.assertEqual(sprite.getpixel((5, 5)), (255, 255, 255, 255))
        with self.assertRaisesRegex(ValueError, 'Unsupported.*background'):
            tool._text_appearance(ink, dict(material, background_style=8))

    def test_approximate_shadow_uses_stored_shadow_alpha(self):
        from PIL import Image
        ink = Image.new('RGBA', (30, 30), (255, 255, 255, 0)); ink.putpixel((15, 15), (255, 255, 255, 255))
        transparent = tool._text_appearance(ink, dict(has_shadow=True, shadow_alpha=0))
        self.assertEqual(transparent.getchannel('A').tobytes(), ink.getchannel('A').tobytes())
        opaque = tool._text_appearance(ink, dict(has_shadow=True, shadow_alpha=1))
        faint = tool._text_appearance(ink, dict(has_shadow=True, shadow_alpha=.25))
        self.assertGreater(opaque.getpixel((15, 17))[3], faint.getpixel((15, 17))[3])

    def test_circle_mask_supported_and_unknown_geometry_rejected(self):
        material = dict(resource_type='circle', config={'width': .8, 'height': .8, 'invert': False})
        mask = tool.circle_mask((100, 100), material)
        self.assertEqual(mask.getpixel((50, 50)), 255)
        self.assertEqual(mask.getpixel((0, 0)), 0)
        for changed in [dict(material, resource_type='rectangle')]+[
                dict(material, config=dict(material['config'], **change)) for change in
                ({'invert': True}, {'feather': .2}, {'centerX': .1}, {'unknown': 1})]:
            with self.subTest(mask=changed), self.assertRaisesRegex(ValueError, 'Unsupported photo mask'):
                tool.circle_mask((100, 100), changed)

    def test_all_card_windows_retain_whole_holds_and_long_one_two_line_cues_selected(self):
        def cue(text, start, duration):
            return dict(role='subtitle', text=text, segment={'id': text, 'target_timerange':
                        {'start': round(start*1e6), 'duration': round(duration*1e6)}})
        plan = {'cards': [dict(id='first', start=1, duration=3), dict(id='second', start=7, duration=5)]}
        rows = [cue('short', 0, 1), cue('Longest single line cue', 4, 6),
                cue('Two lines\nwith longest line', 12, 2)]
        windows = tool._windows(plan, rows, 20)
        self.assertEqual([(w['start'], w['end'], w['full_hold']) for w in windows[:2]], [(1, 4, True), (7, 12, True)])
        self.assertEqual([w['id'] for w in windows[2:]], ['Longest single line cue', 'Two lines\nwith longest line'])
        self.assertEqual(windows[2]['end'], 8)
        with self.assertRaisesRegex(ValueError, 'do not truncate'):
            tool._windows({'cards': [dict(id='huge', start=0, duration=31)]}, [], 40)

    def test_repositioned_subtitle_preview_covers_full_cue_after_card_ends(self):
        plan = {'cards': [dict(id='short-card', start=1, duration=1)],
                'subtitle_template': {'cue_positions': [{'segment_id': 'reviewed-cue', 'y': -.3,
                                                        'review': 'Whole teaching gesture cue reviewed.'}]}}
        row = dict(role='subtitle', text='Short repositioned cue',
                   segment={'id': 'reviewed-cue', 'target_timerange': {'start': 1000000, 'duration': 5000000}})
        windows = tool._windows(plan, [row], 8)
        position = [w for w in windows if w['kind'] == 'subtitle-position']
        self.assertEqual(len(position), 1)
        self.assertEqual((position[0]['start'], position[0]['end'], position[0]['full_hold']), (1, 6, True))
        self.assertGreater(position[0]['end'], windows[0]['end'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Optional integration needs FFmpeg/ffprobe')
    def test_bounded_motion_preview_keeps_inputs_immutable_native_false_full_holds_and_safe_names(self):
        source = self.root/'moving.mkv'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=s=480x270:r=24:d=2', '-c:v', 'ffv1', '-y', str(source)], check=True, capture_output=True)
        project = self.root/'project'; project.mkdir()
        stage = self.root/'stage'; stage.mkdir()
        card_id = '../unsafe card/name'
        mid = identity('fixture', card_id+'/title')
        material = dict(self.material, id=mid, type='text', content=json.dumps({'text': 'Observed wide glyphs WWW'}), text_color='#FFFFFF')
        text = dict(id='text-segment', material_id=mid, clip={'scale': {'x': 1, 'y': 1}, 'transform': {'x': .92, 'y': 0}},
                    target_timerange={'start': 100000, 'duration': 800000})
        draft = dict(id='fixture', duration=1000000, canvas_config={'width': 480, 'height': 270},
                     materials={'texts': [material], 'videos': [dict(id='video', path=str(source), width=480, height=270, type='video')]},
                     tracks=[dict(type='video', segments=[dict(id='video-segment', material_id='video',
                                source_timerange={'start': 500000, 'duration': 500000},
                                target_timerange={'start': 0, 'duration': 1000000})]), dict(type='text', segments=[text])])
        plan = {'cards': [dict(id=card_id, start=.1, duration=.8)]}
        (stage/'draft.json').write_text(json.dumps(draft)); (stage/'plan.json').write_text(json.dumps(plan))
        (stage/'transaction.json').write_text(json.dumps(dict(version=1, project=str(project), before={}, after={}, plan_hash=tool._hash(stage/'plan.json'))))
        calibration = self.root/'calibration.json'
        calibration.write_text(json.dumps(dict(version=1, canvas={'width': 480, 'height': 270}, entries=[self.entry])))
        originals = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        output = self.root/'preview'; manifest = tool.preview(stage, calibration, output)
        self.assertFalse(manifest['native_render_verified'])
        self.assertTrue(manifest['text_bounds'][0]['overflow'])
        self.assertEqual(manifest['frames'], 10)
        self.assertEqual(manifest['windows'][0]['start'], .1)
        self.assertAlmostEqual(manifest['windows'][0]['end'], .9)
        self.assertTrue(manifest['windows'][0]['full_hold'])
        self.assertGreater((output/'preview.mp4').stat().st_size, 1000)
        self.assertTrue(list((output/'holds').glob('window-001-page-*.jpg')))
        self.assertTrue(all(p.read_bytes() == raw for p, raw in originals.items()))
        self.assertEqual(manifest['source_hashes'][str(source)], tool._hash(source))
        self.assertEqual(manifest['calibration_sha256'], tool._hash(calibration))
        from PIL import Image, ImageChops
        pictures = [Image.open(row['file']).crop((0, 0, 480, 270)) for row in manifest['stills']]
        self.assertIsNotNone(ImageChops.difference(pictures[0], pictures[-1]).getbbox(), 'Montage must retain real source motion')
        self.assertTrue(all(path.is_relative_to(output) for path in output.rglob('*')))
        with self.assertRaisesRegex(ValueError, 'fresh folder'):
            tool.preview(stage, calibration, output)


if __name__ == '__main__':
    unittest.main()
