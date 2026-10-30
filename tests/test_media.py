import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'skills/capcut-cinematic-cards/scripts'))


class MappingTest(unittest.TestCase):
    def fixture(self):
        child = {'materials': {'videos': [{'id': 'v', 'path': '##_draftpath_placeholder_abc_##/Resources/a.mp4'}], 'transitions': [{'id': 'fade', 'name': 'Black Fade', 'duration': 1500000}]}, 'tracks': [{'type': 'video', 'segments': [{'id': 'clip', 'material_id': 'v', 'source_timerange': {'start': 30000000, 'duration': 10000000}, 'target_timerange': {'start': 1000000, 'duration': 10000000}, 'extra_material_refs': ['fade']}]}]}
        return {'duration': 20000000, 'materials': {'drafts': [{'id': 'c', 'draft': child}]}, 'tracks': [{'type': 'video', 'segments': [{'id': 'compound', 'material_id': 'none', 'extra_material_refs': ['c'], 'source_timerange': {'start': 2000000, 'duration': 10000000}, 'target_timerange': {'start': 5000000, 'duration': 5000000}}]}]}

    def test_nested_trim_speed_and_placeholder_are_mapped(self):
        from media import flatten
        data = self.fixture(); before = copy.deepcopy(data)
        result = flatten(data, pathlib.Path('/project'))
        source = result['sources'][0]
        self.assertEqual(source['start'], 5)
        self.assertEqual(source['end'], 9.5)
        self.assertEqual(source['source_start'], 31)
        self.assertEqual(source['speed'], 2)
        self.assertEqual(pathlib.Path(source['path']), pathlib.Path('/project/Resources/a.mp4'))
        self.assertEqual(result['transitions'][0]['cut'], 9.5)
        self.assertEqual(result['transitions'][0]['duration'], .75)
        self.assertEqual(data, before)

    def test_reverse_and_curve_speed_are_explicitly_unsupported(self):
        from media import flatten
        data = self.fixture()
        data['tracks'][0]['segments'][0]['reverse'] = True
        result = flatten(data, pathlib.Path('/project'))
        self.assertTrue(result['warnings'])
        self.assertFalse(result['sources'])

    def test_static_image_collection_maps_to_photo_source(self):
        from media import flatten
        data = self.fixture()
        child = data['materials']['drafts'][0]['draft']
        child['materials']['images'] = child['materials'].pop('videos')
        result = flatten(data, pathlib.Path('/project'))
        self.assertEqual(result['sources'][0]['source_type'], 'photo')

    def test_probe_refuses_existing_output_and_unbounded_window(self):
        import tempfile
        from media import probe
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                probe({'duration': 20, 'sources': [], 'warnings': []}, 10, 4, 5, pathlib.Path(root))
            with self.assertRaises(ValueError):
                probe({'duration': 20, 'sources': [], 'warnings': []}, 10, 400, 5, pathlib.Path(root)/'out')

    def test_review_framing_keeps_zoom_pan_and_composes_child_before_parent(self):
        from media import flatten
        data = self.fixture()
        data['canvas_config'] = {'width': 1920, 'height': 1080}
        child = data['materials']['drafts'][0]['draft']
        child['canvas_config'] = data['canvas_config'].copy()
        child['materials']['videos'][0].update(width=1280, height=720)
        leaf = child['tracks'][0]['segments'][0]
        leaf['clip'] = {'scale': {'x': 2, 'y': 2}, 'transform': {'x': .5, 'y': -.5}}
        source = flatten(data, pathlib.Path('/project'))['sources'][0]
        # Output [-1,1] maps to source x[-.75,.25], y[-.25,.75].
        self.assertEqual(source.get('review_framing'),
                         {'status': 'static_uniform', 'crop': [-.75, -.25, .25, .75]})
        leaf['clip'] = {'scale': {'x': 1.5, 'y': 1.5}, 'transform': {'x': .25, 'y': -.25}}
        data['tracks'][0]['segments'][0]['clip'] = {
            'scale': {'x': 2, 'y': 2}, 'transform': {'x': -.5, 'y': .5}}
        source = flatten(data, pathlib.Path('/project'))['sources'][0]
        self.assertEqual(source['review_framing']['crop'], [-1/3, -1/3, 1/3, 1/3])

    def test_review_framing_reports_unsupported_geometry_instead_of_raw_frame_approval(self):
        from media import flatten
        data = self.fixture(); data['canvas_config'] = {'width': 1920, 'height': 1080}
        leaf = data['materials']['drafts'][0]['draft']['tracks'][0]['segments'][0]
        leaf['clip'] = {'rotation': 15}
        source = flatten(data, pathlib.Path('/project'))['sources'][0]
        self.assertEqual(source.get('review_framing', {}).get('status'), 'unsupported')

    def test_unit_geometry_requires_valid_source_dimensions(self):
        from media import review_framing
        for width,height in ((0,0),(1920,0),(-1920,1080),(float('nan'),1080),(True,1080)):
            with self.subTest(width=width,height=height):
                framing=review_framing([],{'width':1920,'height':1080},{'width':width,'height':height})
                self.assertEqual(framing['status'],'unsupported')

    def test_static_overlay_extent_uses_asset_aspect_and_actual_canvas_transform(self):
        from media import flatten
        data = self.fixture(); data['canvas_config'] = {'width': 1600, 'height': 900}
        child = data['materials']['drafts'][0]['draft']
        child['materials']['images'] = child['materials'].pop('videos')
        child['materials']['images'][0].update(width=1000, height=1000)
        child['tracks'][0]['segments'][0]['clip'] = {
            'scale': {'x': .2, 'y': .2}, 'transform': {'x': .5, 'y': -.5}}
        source = flatten(data, pathlib.Path('/project'))['sources'][0]
        self.assertEqual(source.get('review_framing'),
                         {'status': 'static_overlay_extent', 'bounds': [.3875, -.7, .6125, -.3]})
        # CapCut also stores photos in materials.videos with type=photo.
        child['materials']['videos'] = child['materials'].pop('images')
        child['materials']['videos'][0]['type'] = 'photo'
        source = flatten(data, pathlib.Path('/project'))['sources'][0]
        self.assertEqual(source['review_framing']['status'], 'static_overlay_extent')
