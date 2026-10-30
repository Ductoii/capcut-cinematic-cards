"""Read-only source mapping and bounded FFmpeg evidence, not a CapCut renderer."""
import json
import math
import re
import shutil
import subprocess
from bisect import bisect_right
from fractions import Fraction
from pathlib import Path


def review_framing(chain, canvas, material, photo=False):
    """Static same-aspect zoom/pan evidence, not native effects/compositing."""
    def unsupported(reason):
        return dict(status='unsupported', reason=reason)
    def valid_dimensions(*values):
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in values)
    width, height = canvas.get('width', 0), canvas.get('height', 0)
    if not valid_dimensions(width, height):
        return unsupported('Missing canvas dimensions')
    aspect = width/height
    scale, x, y = 1., 0., 0.
    for segment, local_canvas in reversed(chain):
        if local_canvas:
            cw, ch = local_canvas.get('width', width), local_canvas.get('height', height)
            if not valid_dimensions(cw, ch) or abs(cw/ch-aspect) > .0001:
                return unsupported('Nested canvas dimensions/aspect differ')
        clip = segment.get('clip') or {}
        if clip.get('rotation', 0) or any(clip.get('flip', {}).values()):
            return unsupported('Rotation/flip needs separate native geometry review')
        if any(k.get('property_type') not in ('KFTypeAlpha', 'KFTypeVolume') for k in segment.get('common_keyframes', [])):
            return unsupported('Animated geometry needs time-dependent native review')
        sx, sy = (float(clip.get('scale', {}).get(a, 1)) for a in ('x', 'y'))
        tx, ty = (float(clip.get('transform', {}).get(a, 0)) for a in ('x', 'y'))
        if not all(math.isfinite(v) for v in (sx, sy, tx, ty)) or sx <= 0 or abs(sx-sy) > .000001:
            return unsupported('Nonuniform/invalid scale')
        if not photo and (sx < 1 or abs(tx) > sx-1+.00001 or abs(ty) > sx-1+.00001):
            return unsupported('Zoom-out or exposed canvas background needs separate review')
        scale, x, y = sx*scale, sx*x+tx, sx*y+ty
    expected = dict(upper_left_x=0, upper_left_y=0, upper_right_x=1, upper_right_y=0,
                    lower_left_x=0, lower_left_y=1, lower_right_x=1, lower_right_y=1)
    if any(abs(material.get('crop', {}).get(k, v)-v) > .000001 for k, v in expected.items()):
        return unsupported('Material crop needs separate native geometry review')
    sw, sh = material.get('width', 0), material.get('height', 0)
    if not valid_dimensions(sw, sh):
        return unsupported('Missing/invalid source dimensions')
    if photo:
        hx, hy = min(1., sw/sh/aspect)*scale, min(1., aspect/(sw/sh))*scale
        return dict(status='static_overlay_extent', bounds=[x-hx, y-hy, x+hx, y+hy])
    if abs(sw/sh-aspect) > .0001:
        return unsupported('Source fit/aspect is unresolved')
    return dict(status='static_uniform', crop=[(-1-x)/scale, (-1-y)/scale, (1-x)/scale, (1-y)/scale])


def flatten(data, project):
    sources, transitions, warnings = [], [], []

    def walk(draft, offset, scale, bounds, parents, inherited_volume=1, framing=()):
        if len(parents) > 12:
            warnings.append('Nested compound depth exceeds 12; manual mapping needed')
            return
        materials = {item.get('id'): (kind, item) for kind, values in draft.get('materials', {}).items()
                     if isinstance(values, list) for item in values if isinstance(item, dict)}
        for track in draft.get('tracks', []):
            for segment in track.get('segments', []):
                if not segment.get('visible', True):
                    continue
                tr = segment.get('target_timerange') or {}
                ts, td = tr.get('start', 0)/1e6, tr.get('duration', 0)/1e6
                if td <= 0:
                    continue
                start, end = max(bounds[0], offset+ts*scale), min(bounds[1], offset+(ts+td)*scale)
                if start >= end:
                    continue
                refs = [materials[r] for r in segment.get('extra_material_refs', []) if r in materials]
                unsupported = segment.get('reverse') or segment.get('is_loop') or any(kind == 'speeds' and item.get('curve_speed') for kind, item in refs)
                if unsupported:
                    warnings.append(f'Unsupported reverse/loop/curve-speed mapping: {segment.get("id")} at {start:.3f}..{end:.3f}')
                    continue
                sr = segment.get('source_timerange') or {'start': 0, 'duration': td*1e6}
                ss, sd = sr.get('start', 0)/1e6, sr.get('duration', td*1e6)/1e6
                if sd <= 0:
                    continue
                nested = [item for kind, item in refs if kind == 'drafts']
                kind, material = materials.get(segment.get('material_id'), ('', {}))
                if kind == 'drafts':
                    nested.append(material)
                volume = inherited_volume * float(segment.get('volume', 1))
                geometry = framing+((segment, draft.get('canvas_config', data.get('canvas_config', {}))),)
                if nested:
                    for child in nested:
                        if not isinstance(child.get('draft'), dict):
                            warnings.append('External/encrypted compound is unsupported')
                            continue
                        child_scale = scale*td/sd
                        walk(child['draft'], offset+ts*scale-ss*child_scale, child_scale, (start, end), parents+[segment.get('id')], volume, geometry)
                elif kind in ('videos', 'audios', 'images') and material.get('path'):
                    raw = re.sub(r'^##_draftpath_placeholder_[^/\\]+_##[/\\]', '', material['path'])
                    path = Path(raw).expanduser()
                    if not path.is_absolute():
                        path = project/path
                    item = dict(id=segment.get('id'), kind='videos' if kind == 'images' else kind, path=str(path), start=start, end=end,
                                        source_start=ss+(start-(offset+ts*scale))*sd/(td*scale), speed=sd/(td*scale),
                                        volume=volume, parents=parents, source_type='photo' if kind == 'images' else material.get('type'),
                                        has_audio=bool(material.get('has_audio', kind == 'audios')))
                    if kind in ('videos', 'images'):
                        item['review_framing'] = review_framing(geometry, data.get('canvas_config', {}), material,
                                                               kind == 'images' or material.get('type') == 'photo')
                    sources.append(item)
                for ref_kind, item in refs:
                    cut = offset+(ts+td)*scale
                    if ref_kind == 'transitions' and bounds[0] <= cut <= bounds[1]:
                        transitions.append(dict(cut=cut, duration=item.get('duration', 0)/1e6*scale,
                                                name=item.get('name'), segment_id=segment.get('id')))

    walk(data, 0., 1., (0., data['duration']/1e6), [])
    return dict(sources=sorted(sources, key=lambda row: (row['start'], row['kind'])),
                transitions=sorted(transitions, key=lambda row: row['cut']), warnings=warnings)


def run(arguments):
    result = subprocess.run(arguments, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode('utf-8', errors='replace')[-1800:])


def stream_info(ffprobe, path):
    result = subprocess.run([ffprobe, '-v', 'error', '-show_entries',
                             'stream=index,codec_type,duration,avg_frame_rate:format=duration,start_time', '-of', 'json', path],
                            capture_output=True, check=True)
    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    for stream in streams:
        stream['_container_duration'] = data.get('format', {}).get('duration')
        stream['_container_start_time'] = data.get('format', {}).get('start_time', '0')
    return streams


def available_video_sample(ffprobe, path, position, streams, force=False):
    """Only account for a sub-frame audio/container tail; never freeze a bad trim."""
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    try:
        duration = float(video.get('duration') or video['_container_duration'])
        rate = float(Fraction(video.get('avg_frame_rate', '0/1')))
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        duration, rate = None, 0
    if not force and (duration is None or rate <= 0 or position < duration-1/rate-1e-5):
        return position, None
    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                             '-read_intervals', f'{max(0, position-2):.6f}%+4',
                             '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', path],
                            capture_output=True, check=True)
    packets = [p for p in json.loads(result.stdout).get('packets', []) if p.get('pts_time')]
    if not packets:
        raise ValueError('No video samples available at the mapped source tail')
    if any(float(p['pts_time']) > position for p in packets):
        return position, None
    last = max(packets, key=lambda p: float(p['pts_time']))
    sample = float(last['pts_time'])
    interval = float(last.get('duration_time', 0))
    end = sample+interval
    if not (math.isfinite(interval) and interval > 0 and position <= end+interval+1e-5):
        raise ValueError('Mapped source exceeds the video stream by more than one frame; review the trim')
    outside = position >= end
    return sample, dict(requested_source_time=position, source_time=sample,
                        video_duration=end, sample_policy='last_available_video_frame' if outside else 'last_video_frame',
                        note=('Audio/container outlasts video by less than one frame. '
                              'This is an available source sample, not proof of native CapCut frame holding.' if outside else
                              'Requested time falls inside the last video sample; seek at its PTS to avoid an empty EOF extraction.'))


def internal_cuts(ffmpeg, source, left, right):
    """Heuristic scene changes inside one media file, mapped to timeline time."""
    position = source['source_start']+(left-source['start'])*source['speed']
    duration = (right-left)*source['speed']
    result = subprocess.run([ffmpeg, '-v', 'info', '-ss', f'{position:.6f}', '-t', f'{duration:.6f}',
                             '-i', source['path'], '-an', '-vf', "select='gt(scene,0.20)',showinfo",
                             '-f', 'null', '-'], capture_output=True)
    if result.returncode:
        raise ValueError('Source-internal cut detection failed: '+result.stderr.decode('utf8', errors='replace')[-1000:])
    times = [float(t) for t in re.findall(r'\bpts_time:([0-9.eE+-]+)', result.stderr.decode('utf8', errors='replace'))]
    return sorted(set(left+t/source['speed'] for t in times if 0 < t < duration))


def presentation_times(ffprobe, path, left, right):
    """Packet PTS sorted in presentation order, including the active earlier frame."""
    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                             '-read_intervals', f'{max(0, left-2):.6f}%{right+1:.6f}',
                             '-show_entries', 'packet=pts_time', '-of', 'json', path],
                            capture_output=True, check=True)
    values = sorted({float(p['pts_time']) for p in json.loads(result.stdout).get('packets', [])
                     if p.get('pts_time') is not None and math.isfinite(float(p['pts_time']))})
    if not values:
        raise ValueError('Cannot establish video presentation timestamps for this review window')
    return values


def probe(info, at, before, after, out):
    if not all(isinstance(t, (int, float)) and math.isfinite(t) for t in (at, before, after)) or not (0 <= at <= info['duration'] and 0 <= before <= 15 and 0 < after <= 15):
        raise ValueError('Use a bounded review window: up to 15 seconds each side, inside the film')
    out = Path(out).expanduser().resolve()
    if out.exists() or out.is_relative_to(Path(info.get('project', '/nonexistent-project'))):
        raise ValueError('Evidence output must be a fresh folder outside the project')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('FFmpeg and ffprobe are required for media review; core draft editing uses only Python')
    start, end = max(0, at-before), min(info['duration'], at+after)
    selected = [s for s in info['sources'] if s['start'] < end and s['end'] > start]
    if not selected:
        raise ValueError('No mapped sources in this window; inspect unsupported compounds or missing media')
    for source in selected:
        if not Path(source['path']).is_file():
            raise ValueError(f'Missing source media: {source["path"]}')
    out.mkdir(parents=True)
    manifest = dict(start=start, end=end, project_sha256=info['project_sha256'], warnings=list(info['warnings']),
                    source_frames_only=True, note='Frames are uncomposited: review crops, layers, subtitles and effects from draft data too. Audio files are separate stems with timeline offsets.',
                    cut_detection='Timeline source boundaries plus heuristic FFmpeg scene score >0.20; this does not identify people or guarantee every visual cut.',
                    frames=[], audio=[], cuts=[])
    stream_cache = {}
    for index, source in enumerate(selected):
        if source['path'] not in stream_cache:
            stream_cache[source['path']] = stream_info(ffprobe, source['path'])
        streams = stream_cache[source['path']]
        left, right = max(start, source['start']), min(end, source['end'])
        if source['kind'] == 'videos':
            photo = source.get('source_type') == 'photo'
            if not photo:
                origin = float(next((s for s in streams if s.get('codec_type') == 'video'), {}).get('_container_start_time', '0'))
                if not math.isfinite(origin) or abs(origin) > .000001:
                    raise ValueError('Nonzero container timestamp origin is unsupported; do not guess source frame mapping')
            pts = [] if photo else presentation_times(ffprobe, source['path'],
                       source['source_start']+(left-source['start'])*source['speed'],
                       source['source_start']+(right-source['start'])*source['speed'])
            cuts = [] if source.get('source_type') == 'photo' else internal_cuts(ffmpeg, source, left, right)
            for timestamp in cuts:
                manifest['cuts'].append(dict(kind='source-internal', timeline_time=timestamp, source=source['path']))
            if source.get('source_type') != 'photo' and start < source['start'] < end:
                manifest['cuts'].append(dict(kind='timeline-source-boundary', timeline_time=source['start'], source=source['path']))
            video = next((s for s in streams if s.get('codec_type') == 'video'), {})
            try:
                rate = float(Fraction(video.get('avg_frame_rate', '0/1')))
            except (ValueError, ZeroDivisionError):
                rate = 0
            # Timestamp the active frame close enough to each cut for the
            # continuity gate, even when one slow-motion frame lasts >.15s.
            delta = min(.1, 1.1/((rate or 30)*source['speed']))
            times = sorted(set([left+.001, min(right-.001, max(left+.001, at)), max(left+.001, right-.001)] +
                               [left+i*.5 for i in range(1, math.ceil((right-left)*2)) if left+i*.5 < right] +
                               [min(right-.001, max(left+.001, c+d)) for c in cuts for d in (-delta, delta)]))
            for j, timestamp in enumerate(times):
                target = out/f'frame-{index:03d}-{j:03d}.jpg'
                position = source['source_start']+(timestamp-source['start'])*source['speed']
                tail = None
                requested_position = position
                if not photo:
                    position, tail = available_video_sample(ffprobe, source['path'], position, streams)
                    if not tail:
                        active = bisect_right(pts, position+1e-7)-1
                        if active < 0:
                            raise ValueError('No active video presentation frame at the requested source time')
                        position = pts[active]
                # Accurate seeking normally picks the next PTS. Seek just before
                # the chosen active PTS so decimal rounding cannot skip it.
                seek = [] if photo else ['-ss', f'{max(0, position-.000001):.6f}']
                def extract():
                    run([ffmpeg, '-v', 'error', *seek, '-i', source['path'], '-frames:v', '1',
                         '-vf', 'scale=960:-2', '-pix_fmt', 'yuvj420p', '-threads', '1',
                         '-q:v', '3', '-y', str(target)])
                extract()
                if (not target.is_file() or target.stat().st_size == 0) and source.get('source_type') != 'photo':
                    position, tail = available_video_sample(ffprobe, source['path'], position, streams, force=True)
                    if tail:
                        seek = ['-ss', f'{position:.6f}']
                        extract()
                if not target.is_file() or target.stat().st_size == 0:
                    raise ValueError('No frame extracted; source may be out of range')
                frame = dict(file=str(target), timeline_time=timestamp, source=source['path'], source_time=position,
                             source_type=source.get('source_type'), source_segment_id=source.get('id'))
                if not photo and abs(requested_position-position) > 1e-7:
                    frame.update(requested_source_time=requested_position, sample_policy='active_presentation_frame')
                if tail:
                    frame.update(tail)
                    if tail['sample_policy'] == 'last_available_video_frame':
                        warning = f'Last available video sample used for sub-frame tail: {source["path"]}'
                        if warning not in manifest['warnings']:
                            manifest['warnings'].append(warning)
                manifest['frames'].append(frame)
        if any(s.get('codec_type') == 'audio' for s in streams) and source['volume'] > 0:
            speed = source['speed']; filters = []
            while speed > 2:
                filters.append('atempo=2'); speed /= 2
            while speed < .5:
                filters.append('atempo=0.5'); speed *= 2
            filters.extend([f'atempo={speed:.8f}', f'volume={source["volume"]:.8f}'])
            target = out/f'audio-{index:03d}.wav'
            position = source['source_start']+(left-source['start'])*source['speed']
            run([ffmpeg, '-v', 'error', '-ss', f'{position:.6f}', '-t', f'{(right-left)*source["speed"]:.6f}', '-i', source['path'], '-vn', '-af', ','.join(filters), '-ac', '1', '-ar', '16000', '-y', str(target)])
            manifest['audio'].append(dict(file=str(target), timeline_start=left, timeline_end=right, source=source['path']))
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest
