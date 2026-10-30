"""Optional, read-only calibrated reconstruction. This is never a native renderer.

preview(stage, calibration_json, fresh_output) requires Pillow and FFmpeg only
when called. Calibration v1: {"version": 1, "canvas": {"width": W,
"height": H}, "entries": [{"class": "title|detail|subtitle|text",
"font_path": "/absolute/font.ttf", "font_sha256": "...", "font_size": N,
"clip_scale": {"x": N, "y": N}, "letter_spacing": N,
"observed_font_px": N, "tracking_px": N, "line_gap_px": N,
"observation": "reference and measurement method"}]}.

Pixel measurements describe the FINAL observed appearance at calibration.canvas,
including clip scale. No conversion from native font units or second scaling is
performed. Exact matches are required. Font/scale precedence, native kerning,
wrapping, effects, backgrounds and anchor semantics remain unverified.
"""
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path


def _pillow():
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
    except ImportError as exc:
        raise ValueError('Optional preview requires Pillow; core editing does not') from exc
    return Image, ImageChops, ImageDraw, ImageFilter, ImageFont


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def calibration_entry(calibration, role, material, segment):
    """Never extrapolate a calibration to a different native typography tuple."""
    path = str(Path(material['font_path']).expanduser().resolve())
    scale = segment.get('clip', {}).get('scale', {'x': 1, 'y': 1})
    rows = [e for e in calibration.get('entries', [])
            if e.get('class') == role and e.get('font_path') == path
            and e.get('font_size') == material.get('font_size')
            and e.get('clip_scale') == scale
            and e.get('letter_spacing') == material.get('letter_spacing', 0)]
    _need(len(rows) == 1, f'Missing or ambiguous explicit calibration: {role}, {path}, size={material.get("font_size")}, scale={scale}')
    entry = rows[0]
    _need(Path(path).is_file() and entry.get('font_sha256') == _hash(path), 'Calibration font hash mismatch')
    _need(all(_number(entry.get(k)) for k in ('observed_font_px', 'tracking_px', 'line_gap_px'))
          and 0 < entry['observed_font_px'] <= 1000 and entry['line_gap_px'] >= 0,
          'Invalid observed pixel calibration')
    _need(isinstance(entry.get('observation'), str) and entry['observation'].strip(), 'Calibration needs an observation description')
    return entry


def glyph_sprite(text, entry, colour='#FFFFFF'):
    """Return ink and its true alpha bounds, independent of declared text boxes."""
    Image, _, ImageDraw, _, ImageFont = _pillow()
    _need(text and all(c == '\n' or ord(c) >= 32 for c in text), 'Unsupported empty/control-character text')
    font = ImageFont.truetype(entry['font_path'], max(1, round(entry['observed_font_px']*2)))
    tracking = entry['tracking_px']*2
    lines = []
    for line in text.split('\n'):
        _need(bool(line), 'Empty text lines require explicit native layout review')
        positions = [(font.getlength(line[:i])+i*tracking, char) for i, char in enumerate(line)]
        if abs(tracking) < .00001:
            positions = [(0, line)]  # preserve whole-line kerning where possible
        boxes = [(x+font.getbbox(char)[0], font.getbbox(char)[1],
                  x+font.getbbox(char)[2], font.getbbox(char)[3]) for x, char in positions]
        left = math.floor(min(b[0] for b in boxes)); top = min(b[1] for b in boxes)
        right = math.ceil(max(b[2] for b in boxes)); bottom = max(b[3] for b in boxes)
        mask = Image.new('L', (max(1, right-left)+4, max(1, bottom-top)+4))
        draw = ImageDraw.Draw(mask)
        for x, char in positions:
            draw.text((x-left+2, 2-top), char, font=font, fill=255)
        lines.append(mask)
    gap = round(entry['line_gap_px']*2)
    mask = Image.new('L', (max(line.width for line in lines), sum(line.height for line in lines)+gap*(len(lines)-1)))
    y = 0
    for line in lines:
        mask.paste(line, ((mask.width-line.width)//2, y)); y += line.height+gap
    mask = mask.resize((max(1, round(mask.width/2)), max(1, round(mask.height/2))), Image.Resampling.LANCZOS)
    ink = Image.new('RGBA', mask.size, colour); ink.putalpha(mask)
    return ink, mask.getbbox()


def circle_mask(size, material):
    """Support only the reviewed static, centered, unfeathered Circle shape."""
    Image, _, ImageDraw, _, _ = _pillow()
    config = material.get('config', {})
    _need(material.get('resource_type') == 'circle', 'Unsupported photo mask shape')
    allowed = {'width', 'height', 'centerX', 'centerY', 'feather', 'invert', 'rotation', 'expansion', 'roundCorner', 'aspectRatio'}
    _need(not set(config)-allowed, 'Unsupported photo mask config')
    _need(config.get('aspectRatio', 1) == 1 and not config.get('invert') and all(config.get(k, 0) == 0 for k in
          ('centerX', 'centerY', 'feather', 'rotation', 'expansion', 'roundCorner')), 'Unsupported photo mask geometry')
    _need(all(_number(config.get(k)) and 0 < config[k] <= 1 for k in ('width', 'height')),
          'Unsupported photo mask extent')
    mask = Image.new('L', size)
    hw, hh = size[0]*config['width']/2, size[1]*config['height']/2
    ImageDraw.Draw(mask).ellipse((size[0]/2-hw, size[1]/2-hh, size[0]/2+hw, size[1]/2+hh), fill=255)
    return mask


def _text_appearance(ink, material):
    """Approximate native appearance separately from measurable glyph ink."""
    Image, _, _, ImageFilter, _ = _pillow()
    sprite = ink.copy()
    if material.get('has_shadow'):
        opacity = material.get('shadow_alpha', 1)
        _need(_number(opacity) and 0 <= opacity <= 1, 'Unsupported shadow alpha')
        shadow = ink.getchannel('A').filter(ImageFilter.GaussianBlur(2)).point(lambda v: round(v*opacity))
        sprite = Image.new('RGBA', ink.size, 'black'); sprite.putalpha(shadow); sprite.alpha_composite(ink)
    style = material.get('background_style', 0)
    _need(isinstance(style, int) and not isinstance(style, bool) and style in (0, 1), 'Unsupported native background style')
    if style == 1:
        opacity = material.get('background_alpha', 0)
        _need(_number(opacity) and 0 <= opacity <= 1, 'Unsupported background alpha')
        backing = Image.new('RGBA', ink.size, material.get('background_color') or '#000000')
        backing.putalpha(round(255*opacity)); backing.alpha_composite(sprite); sprite = backing
    return sprite


def _alpha(segment, timestamp):
    relative = timestamp-segment['target_timerange']['start']/1e6
    value = segment.get('clip', {}).get('alpha', 1)
    for curve in segment.get('common_keyframes', []):
        if curve.get('property_type') != 'KFTypeAlpha':
            continue
        points = sorted((p['time_offset']/1e6, p['values'][0]) for p in curve['keyframe_list'])
        _need(points and all(_number(t) and _number(v) for t, v in points), 'Invalid alpha keyframes')
        value = points[-1][1]
        if relative <= points[0][0]:
            value = points[0][1]
        else:
            for (a, av), (b, bv) in zip(points, points[1:]):
                if relative <= b:
                    value = av+(bv-av)*(relative-a)/(b-a) if b > a else bv
                    break
    return max(0, min(1, value))


def _windows(plan, texts, duration):
    windows = []
    for card in plan['cards']:
        start, end = card['start'], card['start']+card['duration']
        _need(0 <= start < end <= duration+.000001, 'Card window outside timeline')
        windows.append(dict(kind='card', id=card['id'], start=start, end=min(end, duration), full_hold=True))
    for position in plan.get('subtitle_template', {}).get('cue_positions', []):
        matches = [row for row in texts if row['role'] == 'subtitle' and row['segment']['id'] == position['segment_id']]
        _need(len(matches) == 1, 'Repositioned subtitle must resolve to one visible cue')
        tr = matches[0]['segment']['target_timerange']
        start, end = tr['start']/1e6, (tr['start']+tr['duration'])/1e6
        _need(0 <= start < end <= duration+.000001, 'Repositioned subtitle window outside timeline')
        windows.append(dict(kind='subtitle-position', id=position['segment_id'], start=start,
                            end=min(end, duration), full_hold=True))
    # One longest explicit single-line and two-line cue; no inferred rewrapping.
    for lines in (1, 2):
        candidates = [row for row in texts if row['role'] == 'subtitle' and len(row['text'].split('\n')) == lines]
        if candidates:
            row = max(candidates, key=lambda r: max(map(len, r['text'].split('\n'))))
            tr = row['segment']['target_timerange']; start = tr['start']/1e6
            windows.append(dict(kind='subtitle', id=row['segment']['id'], start=start,
                                end=min(duration, start+tr['duration']/1e6, start+4), full_hold=False))
    _need(windows, 'No card or subtitle windows to preview')
    _need(all(0 < w['end']-w['start'] <= 30 for w in windows) and sum(w['end']-w['start'] for w in windows) <= 180,
          'Preview exceeds bounded limits (30 seconds per hold, 180 total); do not truncate a card hold')
    return windows


def _decode(ffmpeg, source, left, right, width, height, fps):
    crop = source['review_framing']['crop']; l, b, r, top = crop
    seek = source['source_start']+(left-source['start'])*source['speed']
    filters = (f'crop=w=iw*{(r-l)/2}:h=ih*{(top-b)/2}:x=iw*{(l+1)/2}:y=ih*{(1-top)/2}:exact=1,'
               f'scale={width}:{height},setpts=(PTS-STARTPTS)/{source["speed"]},fps={fps}')
    result = subprocess.run([ffmpeg, '-v', 'error', '-ss', str(max(0, seek)), '-i', source['path'],
                             '-t', str(right-left+.1), '-vf', filters, '-an', '-pix_fmt', 'rgb24',
                             '-threads', '1', '-f', 'rawvideo', '-'], capture_output=True)
    _need(result.returncode == 0, 'Source decode failed: '+result.stderr.decode(errors='replace')[-500:])
    frame_size = width*height*3
    _need(len(result.stdout) >= frame_size and len(result.stdout) % frame_size == 0, 'No complete source frames decoded')
    return result.stdout


def preview(directory, calibration_path, out):
    """Write a fresh local reconstruction montage, hold sheets and manifest only."""
    from cards import transaction
    from media import flatten, stream_info
    from native_text import identity
    Image, ImageChops, ImageDraw, _, ImageFont = _pillow()
    directory, project, _ = transaction(directory)
    calibration_path = Path(calibration_path).expanduser().resolve(strict=True)
    out = Path(out).expanduser().resolve()
    _need(not out.exists() and not out.is_relative_to(project) and not out.is_relative_to(directory),
          'Preview output must be a fresh folder outside project and stage')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    _need(ffmpeg and ffprobe, 'Optional preview requires FFmpeg and ffprobe')
    data = json.loads((directory/'draft.json').read_bytes()); plan = json.loads((directory/'plan.json').read_bytes())
    calibration = json.loads(calibration_path.read_bytes())
    _need(calibration.get('version') == 1, 'Unsupported calibration version')
    canvas = calibration.get('canvas', {}); width, height = canvas.get('width'), canvas.get('height')
    _need(all(isinstance(n, int) and not isinstance(n, bool) and 64 <= n <= 1280 and n % 2 == 0 for n in (width, height)) and width >= 480,
          'Calibration canvas needs even dimensions from 64 to 1280')
    native = data['canvas_config']
    _need(abs(width/height-native['width']/native['height']) < .0001, 'Calibration canvas aspect mismatch')
    fps, footer = 12, 48
    materials = {m['id']: m for m in data['materials'].get('texts', [])}
    segments = {s['id']: s for track in data['tracks'] for s in track.get('segments', [])}
    roles = {identity(data['id'], c['id']+'/'+role): role for c in plan['cards'] for role in ('title', 'detail')}
    texts, unsupported = [], []
    for track in data['tracks']:
        if track.get('type') != 'text':
            continue
        for segment in track.get('segments', []):
            if not segment.get('visible', True):
                continue
            material = materials[segment['material_id']]; content = json.loads(material['content'])
            _need(material.get('type') in ('text', 'subtitle'), 'Unsupported text material shape')
            role = roles.get(material['id'], 'subtitle' if material.get('type') == 'subtitle' else 'text')
            clip = segment.get('clip', {})
            _need(not clip.get('rotation') and not any(clip.get('flip', {}).values())
                  and all(k.get('property_type') == 'KFTypeAlpha' for k in segment.get('common_keyframes', [])),
                  'Unsupported animated/rotated text geometry')
            _need(material.get('alignment', 1) == 1 and material.get('typesetting', 0) == 0
                  and len(content.get('styles', [])) <= 1 and not material.get('is_rich_text')
                  and not any(material.get(k, 0) for k in ('border_width', 'bold_width', 'italic_degree', 'underline')),
                  'Unsupported text shape/style')
            entry = calibration_entry(calibration, role, material, segment)
            ink, bounds = glyph_sprite(content['text'], entry, material.get('text_color', '#FFFFFF'))
            transform = clip.get('transform', {})
            xy = (round((transform.get('x', 0)+1)*width/2-ink.width/2),
                  round((1-transform.get('y', 0))*height/2-ink.height/2))
            actual = [bounds[0]+xy[0], bounds[1]+xy[1], bounds[2]+xy[0], bounds[3]+xy[1]] if bounds else None
            sprite = _text_appearance(ink, material)
            if segment.get('extra_material_refs'):
                unsupported.append(dict(segment_id=segment['id'], feature='Native text effects/animations are not evaluated'))
            style = next(iter(content.get('styles', [])), {})
            if (set(style)-{'range', 'size', 'font', 'letter_spacing', 'fill', 'shadows'}
                    or style.get('fill', {}).get('render_type', 'solid') != 'solid'):
                unsupported.append(dict(segment_id=segment['id'], feature='Unknown native text style fields are not evaluated'))
            texts.append(dict(role=role, text=content['text'], segment=segment, sprite=sprite, xy=xy,
                              glyph_bounds=actual, overflow=bool(actual and (actual[0] < 0 or actual[1] < 0 or actual[2] > width or actual[3] > height)),
                              calibration=entry, material_alpha=material.get('text_alpha', 1)*material.get('global_alpha', 1)))
    windows = _windows(plan, texts, data['duration']/1e6)
    _need(all(any(row['segment']['material_id'] == identity(data['id'], card['id']+'/title') for row in texts)
              for card in plan['cards']), 'Planned card has no visible staged title to preview')
    mapping = flatten(data, project)
    _need(not mapping['warnings'], 'Unsupported source mapping: '+'; '.join(mapping['warnings']))
    selected = [s for s in mapping['sources'] if s['kind'] == 'videos' and any(s['start'] < w['end'] and s['end'] > w['start'] for w in windows)]
    videos = [s for s in selected if s.get('source_type') != 'photo']; photos = [s for s in selected if s.get('source_type') == 'photo']
    for source in selected:
        expected = 'static_overlay_extent' if source in photos else 'static_uniform'
        _need(source.get('review_framing', {}).get('status') == expected, 'Unsupported source geometry: '+str(source.get('review_framing')))
        _need(Path(source['path']).is_file(), 'Missing source media: '+source['path'])
        if source in videos:
            streams = stream_info(ffprobe, source['path'])
            origin = float(next((s for s in streams if s.get('codec_type') == 'video'), {}).get('_container_start_time', 0))
            _need(abs(origin) < .000001, 'Nonzero container timestamp origin is unsupported')
            _need(not segments.get(source['id'], {}).get('enable_video_mask'), 'Moving source masks are unsupported')
        if source.get('parents'):
            unsupported.append(dict(segment_id=source['id'], feature='Nested source opacity/effects/layer order are not reproduced'))
        segment = segments.get(source['id'], {})
        if any(segment.get(k) for k in segment if k.startswith('enable_') and k != 'enable_video_mask'):
            unsupported.append(dict(segment_id=source['id'], feature='Enabled native source adjustments/effects are not evaluated'))
        known_refs = {m.get('id') for kind in ('common_mask', 'speeds', 'drafts') for m in data['materials'].get(kind, [])}
        unknown_refs = [ref for ref in segment.get('extra_material_refs', []) if ref not in known_refs]
        if unknown_refs:
            unsupported.append(dict(segment_id=source['id'], feature='Native source resources are not evaluated', refs=unknown_refs))
    for i, source in enumerate(videos):
        _need(not any(max(source['start'], other['start'], w['start']) < min(source['end'], other['end'], w['end'])
                      for other in videos[i+1:] for w in windows), 'Overlapping moving source compositing is unsupported')
    masks = {m['id']: m for m in data['materials'].get('common_mask', [])}
    photo_layers = []
    for source in photos:
        _need(not source['parents'] and source['id'] in segments, 'Nested photo masks/layers are unsupported')
        segment = segments[source['id']]; l, b, r, top = source['review_framing']['bounds']
        size = (max(1, round((r-l)*width/2)), max(1, round((top-b)*height/2)))
        with Image.open(source['path']) as opened:
            image = opened.convert('RGBA').resize(size, Image.Resampling.LANCZOS)
        if segment.get('enable_video_mask'):
            refs = [masks[k] for k in segment.get('extra_material_refs', []) if k in masks]
            _need(len(refs) == 1, 'Photo mask must resolve to one Circle material')
            image.putalpha(ImageChops.multiply(image.getchannel('A'), circle_mask(size, refs[0])))
        photo_layers.append((source, segment, image, (round((l+1)*width/2), round((1-top)*height/2))))
    for transition in mapping['transitions']:
        if any(w['start'] <= transition['cut'] <= w['end'] for w in windows):
            unsupported.append(dict(feature='Native transition not evaluated', **transition))
    source_hashes = {s['path']: _hash(s['path']) for s in selected}
    input_hashes = {str(p): _hash(p) for p in (directory/'draft.json', directory/'plan.json', directory/'transaction.json', calibration_path)}
    out.mkdir(parents=True); (out/'stills').mkdir(); (out/'holds').mkdir()
    try:
        label_font = ImageFont.load_default(size=14)
    except TypeError:
        label_font = ImageFont.load_default()
    process = subprocess.Popen([ffmpeg, '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height+footer}',
                                '-r', str(fps), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                                '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-n', str(out/'preview.mp4')],
                               stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    total = 0; receipts = []; sampling_notes = []
    try:
        for index, window in enumerate(windows):
            window['preview_start'] = total/fps
            pool = []
            for source in videos:
                left, right = max(window['start'], source['start']), min(window['end'], source['end'])
                if left < right:
                    pool.append((source, left, _decode(ffmpeg, source, left, right, width, height, fps)))
            count = math.ceil((window['end']-window['start'])*fps-1e-8)
            samples = sorted(set([0, count-1]+list(range(0, count, max(1, fps//2)))))
            thumbnails = []
            gap_reported = False
            for frame_index in range(count):
                timestamp = window['start']+frame_index/fps
                picture = Image.new('RGBA', (width, height), 'black')
                if not gap_reported and not any(source['start'] <= timestamp < source['end'] for source, _, _ in pool):
                    unsupported.append(dict(window=index, timeline_time=timestamp,
                                            feature='No moving background mapped; uncovered picture uses black before photo overlays'))
                    gap_reported = True
                for source, left, frames in pool:
                    if source['start'] <= timestamp < source['end']:
                        frame_size = width*height*3; available = len(frames)//frame_size
                        wanted = max(0, math.floor((timestamp-left)*fps+.00001)); chosen = min(available-1, wanted)
                        if chosen != wanted:
                            sampling_notes.append(dict(window=index, timeline_time=timestamp, policy='last_decoded_frame', source=source['path']))
                        picture = Image.frombytes('RGB', (width, height), frames[chosen*frame_size:(chosen+1)*frame_size]).convert('RGBA')
                        if source['id'] in segments:
                            opacity = _alpha(segments[source['id']], timestamp)
                            if opacity < 1:
                                black = Image.new('RGBA', picture.size, 'black')
                                picture.putalpha(round(opacity*255)); black.alpha_composite(picture); picture = black
                for source, segment, image, xy in photo_layers:
                    if source['start'] <= timestamp < source['end']:
                        layer = image.copy(); opacity = _alpha(segment, timestamp)
                        layer.putalpha(layer.getchannel('A').point(lambda v: round(v*opacity))); picture.alpha_composite(layer, xy)
                for row in texts:
                    segment = row['segment']; tr = segment['target_timerange']
                    if tr['start']/1e6 <= timestamp < (tr['start']+tr['duration'])/1e6:
                        layer = row['sprite'].copy(); opacity = _alpha(segment, timestamp)*row['material_alpha']
                        layer.putalpha(layer.getchannel('A').point(lambda v: round(v*opacity))); picture.alpha_composite(layer, row['xy'])
                canvas = Image.new('RGB', (width, height+footer), (18, 18, 18)); canvas.paste(picture, (0, 0))
                draw = ImageDraw.Draw(canvas)
                draw.text((8, height+5), f'Window {index+1:03d} | timeline {timestamp:.3f}s', font=label_font, fill='white')
                draw.text((8, height+25), 'LOCAL RECONSTRUCTION | native render unverified', font=label_font, fill='white')
                process.stdin.write(canvas.tobytes()); total += 1
                if frame_index in samples:
                    path = out/'stills'/f'window-{index+1:03d}-frame-{frame_index:05d}.jpg'; canvas.save(path, quality=92)
                    receipts.append(dict(window=index, timeline_time=timestamp, file=str(path)))
                    thumb_picture = picture.convert('RGB'); thumb_picture.thumbnail((480, 432))
                    thumb = Image.new('RGB', (480, thumb_picture.height+footer), (18, 18, 18)); thumb.paste(thumb_picture)
                    thumb_draw = ImageDraw.Draw(thumb)
                    thumb_draw.text((8, thumb_picture.height+5), f'Window {index+1:03d} | timeline {timestamp:.3f}s', font=label_font, fill='white')
                    thumb_draw.text((8, thumb_picture.height+25), 'LOCAL RECONSTRUCTION | native unverified', font=label_font, fill='white')
                    thumbnails.append(thumb)
            # Every hold sample is retained; sheets paginate instead of silently dropping late samples.
            for page in range(0, len(thumbnails), 12):
                group = thumbnails[page:page+12]; tw, th = group[0].size
                sheet = Image.new('RGB', (tw*3, th*math.ceil(len(group)/3)), (18, 18, 18))
                for n, image in enumerate(group):
                    sheet.paste(image, ((n % 3)*tw, (n//3)*th))
                sheet.save(out/'holds'/f'window-{index+1:03d}-page-{page//12+1:02d}.jpg', quality=92)
            window['preview_end'] = total/fps
        process.stdin.close()
        stderr = process.stderr.read(); code = process.wait()
        process.stderr.close()
        _need(code == 0, 'Preview encoding failed: '+stderr.decode(errors='replace')[-500:])
    except BaseException:
        process.kill(); process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stderr.close()
        raise
    _need(all(_hash(p) == digest for p, digest in {**input_hashes, **source_hashes}.items()), 'Preview inputs changed during rendering')
    manifest = dict(version=1, native_render_verified=False, reconstruction=True, preview=str(out/'preview.mp4'),
                    fps=fps, frames=total, duration=total/fps, picture_size=[width, height], footer_height=footer,
                    output_size=list(canvas.size), windows=windows, stills=receipts,
                    source_hashes=source_hashes, input_hashes=input_hashes, calibration_sha256=_hash(calibration_path),
                    text_bounds=[{k: r[k] for k in ('role', 'text', 'glyph_bounds', 'overflow', 'calibration')} | {'segment_id': r['segment']['id']} for r in texts],
                    unsupported=unsupported, sampling_notes=sampling_notes,
                    uncertainties=['Reconstruction cannot satisfy native playback/render proof.',
                      'Observed typography is specific to font bytes/native size/clip scale/spacing; native uniform-scale precedence is unresolved.',
                      'Glyph alpha bounds are Pillow measurements, never declared rectangles; native kerning/anchors/wrapping may differ.',
                      'Only explicit newlines are rendered. No automatic shrinking or inferred native wrapping.',
                      'Shadow and background approximations; native animation/effect/transition multiplication and easing are not evaluated.',
                      'Photo overlays are placed above moving footage and below text; native layer-order parity is unverified.',
                      'Silent 12 fps montage uses real trimmed constant-speed source motion; source frame phase may differ from native playback.'])
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory'); parser.add_argument('calibration'); parser.add_argument('out')
    args = parser.parse_args()
    result = preview(args.directory, args.calibration, args.out)
    print(json.dumps({'preview': result['preview'], 'native_render_verified': False}))
