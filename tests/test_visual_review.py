import copy
import json
import pathlib
import shutil
import subprocess
import unittest
from unittest import mock
import test_cards


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg needed for actual source sheets')
class VisualReviewTest(unittest.TestCase):
    setUp = test_cards.CardsTest.setUp
    stage = test_cards.CardsTest.stage
    cut_manifest_fixture = test_cards.CardsTest.cut_manifest_fixture

    def camera_stage(self, rotation=0, photo=False, context_video=True, scale=2):
        video = self.project/'camera.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=160x90:r=1,drawbox=x=0:y=0:w=80:h=90:color=red:t=fill',
                        '-t', '20', '-c:v', 'mpeg4', '-y', str(video)], check=True)
        image = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', str(video),
                                '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'],
                               capture_output=True, check=True).stdout
        source=video
        if photo:
            source=self.project/'still.jpg';source.write_bytes(image)
        child = self.original['materials']['drafts'][0]['draft']
        child['materials']['videos'] = [dict(id='camera', path=str(source), width=160, height=90,
                                            type='photo' if photo else 'video')]
        child['tracks'].append(dict(type='video', segments=[dict(id='camera-segment', material_id='camera',
            target_timerange=dict(start=0, duration=20000000), source_timerange=dict(start=0, duration=20000000),
            clip=dict(scale=dict(x=scale, y=scale), transform=dict(x=.5, y=-.5), rotation=rotation))]))
        if photo and context_video:
            # Footage elsewhere in the project must not suppress this still hold.
            child['materials']['videos'].append(dict(id='context',path=str(video),width=160,height=90,type='video'))
            child['tracks'].append(dict(type='video',segments=[dict(id='context-segment',material_id='context',
                target_timerange=dict(start=0,duration=5000000),source_timerange=dict(start=0,duration=5000000))]))
        for p in self.paths:
            p.write_text(json.dumps(self.original))
        self.plan['project_sha256'] = self.tool.digest(self.indexed/'draft_info.json')
        manifest, rows = self.cut_manifest_fixture()
        for row in rows:
            pathlib.Path(row['file']).write_bytes(image)
            row.update(source=str(source), source_segment_id='camera-segment',source_type='photo' if photo else 'video')
        if photo and context_video:
            context=self.root/'earlier-footage.jpg';context.write_bytes(image)
            rows.append(dict(file=str(context),timeline_time=4,source=str(video),source_time=4,
                             source_type='video',source_segment_id='context-segment'))
        value = self.tool.read(manifest); value['frames'] = rows; manifest.write_text(json.dumps(value))
        self.plan['version'] = 2; self.plan['cards'][0]['duration'] = 2
        return self.stage()

    def test_staged_review_applies_actual_camera_crop_before_card_rectangle(self):
        stage = self.camera_stage()
        output = self.tool.review_bundle(stage, self.root/'camera-review')
        bundle = self.tool.read(output['bundle'])
        frame = bundle['facts']['cards'][0]['frames'][0]
        self.assertEqual(frame.get('review_framing'), {'status': 'static_uniform', 'crop': [-.75, -.25, .25, .75]})
        displayed = bundle['pages'][0]['display_frames'][0]['file']
        geometry = bundle['display_geometry']
        self.assertEqual(geometry['picture_width'], 960)
        self.assertEqual(geometry['picture_height'], 540)
        stream = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=width,height', '-of', 'json', displayed],
                                capture_output=True, check=True)
        dimensions = json.loads(stream.stdout)['streams'][0]
        self.assertEqual(dimensions['width'], geometry['picture_width'])
        self.assertEqual(dimensions['height'], geometry['picture_height'] + geometry['footer_height'])
        # Labels belong below the complete picture, rather than hiding its top/edges.
        caption = bundle['pages'][0]['display_frames'][0]['label']
        self.assertIn('IN CARD', caption)
        self.assertIn('CONTEXT', bundle['pages'][0]['display_frames'][-1]['label'])
        self.assertIn('CYAN = IMAGE OVERLAY', bundle['display_legend'])
        footer = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', displayed,
                                 '-vf', 'crop=iw:56:0:540', '-frames:v', '1',
                                 '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                capture_output=True, check=True).stdout
        self.assertGreater(sum(v > 180 for v in footer), 100)
        for display, expected_green in [(bundle['pages'][0]['display_frames'][0], True),
                                         (bundle['pages'][0]['display_frames'][-1], False)]:
            edge = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', display['file'],
                                   '-vf', 'crop=2:2:96:378,scale=1:1', '-frames:v', '1',
                                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                  capture_output=True, check=True).stdout
            # Yellow declaration while active; the red source stays unobscured in context.
            self.assertGreater(edge[0], 180)
            self.assertEqual(edge[1] > 150, expected_green)
        pixel = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', displayed,
                                '-vf', 'crop=2:2:480:270,scale=1:1', '-frames:v', '1',
                                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
        # Center of the output sees the red source-left half, not raw blue center.
        self.assertGreater(pixel[0], 200); self.assertLess(pixel[2], 60)

    def test_review_refuses_unsupported_camera_geometry_before_generating_approval_sheets(self):
        stage = self.camera_stage(rotation=10)
        with self.assertRaisesRegex(ValueError, 'framing|geometry'):
            self.tool.review_bundle(stage, self.root/'unsupported-camera-review')

    def test_full_canvas_still_hold_can_be_reviewed_with_actual_geometry(self):
        stage=self.camera_stage(photo=True)
        output=self.tool.review_bundle(stage,self.root/'photo-review')
        bundle=self.tool.read(output['bundle'])
        frames=bundle['facts']['cards'][0]['frames']
        self.assertTrue(any(f['inside_hold'] for f in frames))
        self.assertTrue(all(pathlib.Path(f['source']).name=='still.jpg' for f in frames))
        displayed=bundle['pages'][0]['display_frames'][0]['file']
        pixel=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',displayed,
            '-vf','crop=2:2:iw/2:ih/2,scale=1:1','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],
            capture_output=True,check=True).stdout
        self.assertGreater(pixel[0],200);self.assertLess(pixel[2],60)

    def test_still_only_project_produces_review_frames(self):
        stage=self.camera_stage(photo=True,context_video=False)
        output=self.tool.review_bundle(stage,self.root/'still-only-review')
        bundle=self.tool.read(output['bundle'])
        self.assertTrue(bundle['pages'][0]['display_frames'])

    def test_partial_photo_extent_is_not_stretched_to_fake_a_full_canvas(self):
        stage=self.camera_stage(photo=True,scale=.5)
        with self.assertRaisesRegex(ValueError,'canvas background'):
            self.tool.review_bundle(stage,self.root/'partial-photo-review')

    def fixture(self):
        manifest, rows = self.cut_manifest_fixture()
        image = subprocess.run([shutil.which('ffmpeg'), '-v','error','-f','lavfi','-i',
                                'color=c=navy:s=160x90:r=1','-frames:v','1','-f','image2pipe',
                                '-vcodec','mjpeg','-'],capture_output=True,check=True).stdout
        for row in rows:
            pathlib.Path(row['file']).write_bytes(image)
        extra = self.root/'unselected-between-samples.jpg';extra.write_bytes(image)
        value=self.tool.read(manifest)
        value['frames'].append(dict(file=str(extra),timeline_time=9.25,source='fixture-video.mp4',source_time=1.25,source_type='video'))
        manifest.write_text(json.dumps(value))
        self.plan['version']=2;self.plan['cards'][0]['duration']=2
        stage=self.stage()
        output=self.tool.review_bundle(stage,self.root/'review')
        bundle=pathlib.Path(output['bundle']);facts=self.tool.read(bundle)['facts']
        verdict=dict(version=1,independent=True,reviewer='Separate fixture reviewer',bundle=str(bundle),
                     bundle_sha256=self.tool.digest(bundle),native_render_verified=False,cards=[])
        for card in facts['cards']:
            verdict['cards'].append(dict(id=card['id'],reading_time_passed=True,first_appearance_passed=True,
                reading_time_review='Duration reviewed.',first_appearance_review='Earlier raw frames checked.',
                frames=[dict(file=f['file'],observation='Fixture observation; this test checks protocol, not image identity.',
                             subjects=['mira'],associated_characters=['mira'],layout_passed=True) for f in card['frames']]))
        path=self.root/'verdict.json';path.write_text(json.dumps(verdict))
        return stage,bundle,path,verdict,extra

    def test_explicit_rejection_of_reading_time_or_first_entrance_blocks_apply(self):
        stage,bundle,path,original,extra=self.fixture()
        for field in ('reading_time_passed','first_appearance_passed'):
            verdict=copy.deepcopy(original);verdict['cards'][0][field]=False
            path.write_text(json.dumps(verdict))
            with self.assertRaisesRegex(ValueError,'reading time|first entrance'):
                self.tool.apply(stage,path)

    def test_bundle_covers_real_unselected_intermediate_frame_and_neutral_staged_facts(self):
        stage,bundle,path,verdict,extra=self.fixture()
        data=self.tool.read(bundle)
        self.assertIn(str(extra),[f['file'] for f in data['facts']['cards'][0]['frames']])
        self.assertEqual(data['facts']['cards'][0]['lines']['title']['text'],self.plan['cards'][0]['title'])
        self.assertNotIn('visual_review',data['facts']['cards'][0])
        page=pathlib.Path(data['pages'][0]['sheet'])
        self.assertTrue(page.read_bytes().startswith(b'\xff\xd8\xff'))
        self.tool.validate_visual_review(stage,path)
        with mock.patch.object(self.tool,'editor_running',return_value=False):
            self.assertTrue(self.tool.apply(stage,path)['verified'])

    def test_wrong_person_or_label_association_blocks_apply_without_writes(self):
        stage,bundle,path,verdict,extra=self.fixture()
        before=[p.read_bytes() for p in self.paths]
        inside=next(f['file'] for f in self.tool.read(bundle)['facts']['cards'][0]['frames'] if f['inside_hold'])
        row=next(r for r in verdict['cards'][0]['frames'] if r['file']==inside)
        for subjects,associated in [(['leo'],['leo']),(['mira','leo'],['leo'])]:
            row.update(subjects=subjects,associated_characters=associated)
            path.write_text(json.dumps(verdict))
            with self.assertRaisesRegex(ValueError,'identity/label association'):
                self.tool.apply(stage,path)
            self.assertEqual([p.read_bytes() for p in self.paths],before)

    def test_changed_fullsize_display_invalidates_the_independent_review(self):
        stage,bundle,path,verdict,extra=self.fixture()
        display=pathlib.Path(self.tool.read(bundle)['pages'][0]['display_frames'][0]['file'])
        display.write_bytes(display.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'display frame changed'):
            self.tool.validate_visual_review(stage,path)

    def test_collision_incomplete_observation_and_changed_review_frame_are_rejected(self):
        stage,bundle,path,original,extra=self.fixture()
        verdict=copy.deepcopy(original)
        inside=next(f['file'] for f in self.tool.read(bundle)['facts']['cards'][0]['frames'] if f['inside_hold'])
        next(r for r in verdict['cards'][0]['frames'] if r['file']==inside)['layout_passed']=False
        path.write_text(json.dumps(verdict))
        with self.assertRaisesRegex(ValueError,'rejected card layout'):
            self.tool.apply(stage,path)
        verdict=copy.deepcopy(original);verdict['cards'][0]['frames'].pop();path.write_text(json.dumps(verdict))
        with self.assertRaisesRegex(ValueError,'observe every'):
            self.tool.apply(stage,path)
        path.write_text(json.dumps(original));extra.write_bytes(extra.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'stale'):
            self.tool.apply(stage,path)
