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
