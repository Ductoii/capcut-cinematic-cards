#!/usr/bin/env python3
"""Plan-bound, reversible native CapCut card edits. Python 3.10+, no UI control."""
import argparse
import contextlib
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from native_text import identity, make_text
from styles import resolve_style

STATE = '.capcut-cards-state.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(path):
    path = Path(path)
    if not path.exists():
        return None
    signature = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            signature.update(chunk)
    return signature.hexdigest()


def object_hash(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        require(isinstance(value, dict), f'Expected a JSON object: {path}')
        return value
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Unreadable JSON or encrypted CapCut draft: {path}') from exc


def load(project):
    project = Path(project).expanduser().resolve(strict=True)
    root = project/'draft_info.json'
    index = project/'Timelines/project.json'
    active = root
    if index.exists():
        timeline = read(index).get('main_timeline_id', '')
        require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', timeline)), 'Unsafe or missing main timeline pointer')
        active = project/'Timelines'/timeline/'draft_info.json'
        require(active.resolve().is_relative_to(project), 'Main timeline escapes project')
    elif (project/'Timelines').is_dir():
        require(not list((project/'Timelines').glob('*/draft_info.json')), 'Ambiguous timeline without a main pointer')
    require(not active.is_symlink() and not root.is_symlink(), 'Symlinked draft files are not supported')
    raw_hash = digest(active)
    data = read(active)
    require(data.get('version') == 360000, 'Unsupported draft schema; only unencrypted 360000 is implemented')
    require(0 < float(data.get('fps', 0)) <= 240, 'Invalid fps')
    require(data.get('duration', 0) > 0 and isinstance(data.get('tracks'), list) and isinstance(data.get('materials'), dict), 'Incomplete draft')
    if root.exists() and root != active:
        require(read(root) == data, 'Root mirror differs from the indexed main timeline; refusing to guess')
    require(digest(active) == raw_hash, 'Project changed while reading')
    paths = []
    for directory in dict.fromkeys([project, active.parent]):
        for name in ('draft_info.json', 'draft_info.json.bak', 'template-2.tmp'):
            path = directory/name
            if path.exists():
                require(not path.is_symlink() and path.resolve().is_relative_to(project), 'Unsafe draft mirror')
                paths.append(str(path.relative_to(project)))
    return project, active, data, paths, raw_hash


def strip_owned(data, state):
    base = copy.deepcopy(data)
    if state:
        require(state.get('version') == 1 and state.get('project_id') == data.get('id'), 'Incompatible card ownership state')
        for collection, key in [(base['tracks'], 'tracks'), (base['materials'].get('texts', []), 'materials')]:
            owned = state[key]
            found = {item['id']: item for item in collection if item.get('id') in owned}
            require(set(found) == set(owned), 'Owned cards were removed or changed manually')
            require(all(object_hash(found[ident]) == signature for ident, signature in owned.items()), 'Owned cards changed manually; preserve those edits')
            collection[:] = [item for item in collection if item.get('id') not in owned]
        if state.get('texts_container_created'):
            require(not base['materials'].get('texts'), 'New unowned text found in created text collection')
            base['materials'].pop('texts', None)
    return base


def inspect(project):
    from media import flatten
    project, active, data, paths, signature = load(project)
    return dict(project=str(project), active_timeline=str(active), project_sha256=signature, schema=data['version'],
                duration=data['duration']/1e6, fps=data['fps'], canvas=data.get('canvas_config'), mirrors=paths,
                tracks=[{'id': t.get('id'), 'name': t.get('name'), 'type': t['type'], 'segments': len(t.get('segments', []))} for t in data['tracks']],
                ownership=ownership_report(data, read(project/STATE) if (project/STATE).exists() else None,
                                           signature, digest(project/STATE)), **flatten(data, project))


def ownership_report(data, state, signature, state_hash):
    """A review snapshot, never permission to silently accept edited titles."""
    report = dict(project_sha256=signature, state_sha256=state_hash,
                  tracks={}, materials={}, changed={}, missing={})
    if not state:
        report['status'] = 'unmanaged'
        return report
    require(state.get('project_id') == data.get('id') and state.get('version') == 1,
            'Incompatible card ownership state')
    for key, values in [('tracks', data['tracks']), ('materials', data['materials'].get('texts', []))]:
        found = [v for v in values if v.get('id') in state[key]]
        require(len({v['id'] for v in found}) == len(found), 'Duplicate owned ID; review manually')
        report[key] = {v['id']: object_hash(v) for v in found}
        report['missing'][key] = sorted(set(state[key])-set(report[key]))
        report['changed'][key] = sorted(i for i, h in report[key].items() if h != state[key][i])
    report['status'] = ('missing' if any(report['missing'].values()) else
                        'changed' if any(report['changed'].values()) else 'exact')
    return report


def reviewed_state(data, state, signature, state_hash, plan):
    require(state is not None, 'No owned titles to restyle; use stage for initial cards')
    report = ownership_report(data, state, signature, state_hash)
    require(report['status'] != 'missing', 'Owned cards were removed; preserve those edits and review separately')
    segments = [(s.get('material_id'), s.get('id')) for t in data['tracks'] if t['id'] in state['tracks']
                for s in t.get('segments', [])]
    expected = {(ident, identity(ident, 'segment')) for ident in state['materials']}
    require(len(segments) == len(expected) and set(segments) == expected,
            'Owned track segment membership changed; do not reclaim removed or user-added segments')
    if report['status'] == 'changed':
        review = plan.get('ownership_review', {})
        require(isinstance(review, dict) and isinstance(review.get('findings'), str) and
                review['findings'].strip(), 'Owned titles changed; compare the previous stage and record ownership_review findings')
        require(all(review.get(k) == report[k] for k in
                    ('project_sha256', 'state_sha256', 'tracks', 'materials')),
                'Ownership review is stale or incomplete; inspect and review again')
    updated = copy.deepcopy(state)
    updated.update(tracks=report['tracks'], materials=report['materials'])
    if any(m.get('id') not in state['materials'] for m in data['materials'].get('texts', [])):
        # A user-added title now owns the collection too; never remove that collection.
        updated['texts_container_created'] = False
    return updated


def validate_character_review(plan, cards):
    review = plan.get('character_review')
    if review is None:
        require(not plan.get('introduce_characters'), 'List every principal in character_review before staging introductions')
        return
    require(isinstance(review, list) and bool(review), 'character_review must list the principal cast')
    names, introduced = set(), set()
    by_id = {c['id']: c for c in cards}
    for entry in review:
        require(isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name'].strip(),
                'Each principal needs a confirmed name')
        ident = entry.get('id')
        require(isinstance(ident, str) and ident and ident not in names, 'Each principal needs a unique ID')
        names.add(ident)
        if entry.get('status') == 'introduced':
            card = by_id.get(entry.get('card_id'), {})
            require(card.get('kind') == 'character' and ident in card.get('characters', []),
                    'Introduced principal must link to a character card listing their ID')
            introduced.add(ident)
        else:
            require(entry.get('status') == 'omitted' and isinstance(entry.get('reason'), str) and
                    entry['reason'].strip(), 'Omitted principal needs a specific reason, not a silent omission')
    linked_ids = []
    for card in cards:
        if card.get('kind') != 'character':
            continue
        members = card.get('characters')
        require(isinstance(members, list) and members and all(isinstance(i, str) and i for i in members),
                'Each character card needs a list of principal IDs')
        linked_ids.extend(members)
    require(len(linked_ids) == len(set(linked_ids)), 'Introduce each principal once; use a shared pair card when appropriate')
    linked = set(linked_ids)
    require(linked == introduced, 'Character card cast IDs must match introduced principals in character_review')


def number(value, name):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f'Invalid {name}')
    return value


def validate_plan(plan, data, signature, font):
    require(plan.get('version') == 1, 'Plan version must be 1')
    require(plan.get('project_sha256') == signature, 'Project changed; regenerate the plan from current inspection')
    require(font.is_file() and font.read_bytes()[:4] in (b'\x00\x01\x00\x00', b'OTTO', b'ttcf', b'true'), 'Readable local TTF/OTF/TTC font required')
    cards = copy.deepcopy(plan.get('cards', []))
    require(isinstance(cards, list) and cards, 'Choose at least one necessary card; otherwise leave the project unchanged')
    fps = float(data['fps'])
    evidence = {str(font): digest(font)}
    ids = set()
    protected = plan.get('protected_ranges', [])
    require(isinstance(protected, list), 'protected_ranges must be a list')
    for interval in protected:
        start, end = number(interval['start'], 'protected start'), number(interval['end'], 'protected end')
        require(0 <= start < end <= data['duration']/1e6 and interval.get('reason'), 'Invalid protected range')
    for card in cards:
        require(card.get('kind', 'time-location') in ('time', 'location', 'time-location', 'character', 'ending'), 'Unknown card kind')
        selected_style = {**plan.get('style', {}), **card.get('style', {})}
        defaults = {}
        if card.get('kind') == 'character':
            defaults = dict(title_size=6.2, detail_size=3.8, title_spacing=.08, detail_spacing=.12)
            if selected_style.get('theme', 'heritage-drama') == 'heritage-drama':
                defaults['detail_color'] = '#D4CDBE'
            if card.get('detail'):
                card.setdefault('y', -.64 if card.get('layout', 'lower-left') == 'lower-left' else .035)
        card['_style'] = resolve_style({**defaults, **selected_style})
        ident = card.get('id', '')
        require(bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', ident)) and ident not in ids, 'Each card needs a unique stable id')
        ids.add(ident)
        for key, limit in [('title', 32), ('detail', 48)]:
            text = card.get(key, '')
            require(isinstance(text, str) and len(text) <= limit and all(ord(ch) >= 32 for ch in text), f'Use a concise single-line {key}')
        require(bool(card['title'].strip()), 'Card title is blank')
        start = number(card['start'], 'start')
        duration = number(card.get('duration', 3.2), 'duration')
        require(2.8 <= duration <= 8, 'Allow reading time: duration must be 2.8–8 seconds, normally 3.2–3.6')
        card['_start_us'] = round(round(start*fps)*1e6/fps)
        card['_end_us'] = round(round((start+duration)*fps)*1e6/fps)
        left, right = card['_start_us']/1e6, card['_end_us']/1e6
        require(0 <= left < right <= data['duration']/1e6, 'Card falls outside project duration')
        require(card.get('layout', 'lower-left') in ('lower-left', 'center'), 'Unknown layout')
        for key, default in [('x', -.52), ('y', -.66)]:
            require(-.82 <= number(card.get(key, default), key) <= .82, 'Keep text within the frame safe area')
        default_y = -.66 if card.get('layout', 'lower-left') == 'lower-left' else .035
        require(not card.get('detail') or card.get('y', default_y) - .13 >= -.82, 'Detail text falls outside the safe area')
        for interval in protected:
            require(right <= interval['start']-.15 or left >= interval['end']+.15, f'Card overlaps protected dialogue/reaction: {interval["reason"]}')
        proof = card.get('evidence', {})
        require(isinstance(proof, dict) and proof.get('visual_review') and proof.get('dialogue_review'), 'Review actual images and dialogue, recording findings')
        if card.get('kind') == 'character':
            require(proof.get('character_identity') and proof.get('first_appearance'), 'Character identity and first appearance must be reviewed; do not invent a name from a face')
            omission = proof.get('role_omission_reason')
            require(card.get('detail', '').strip() or (isinstance(omission, str) and omission.strip()), 'Character role required in detail; document role_omission_reason for names-only requests, unknown roles or spoilers')
        require(number(proof.get('start'), 'review start') <= left and number(proof.get('end'), 'review end') >= right, 'Evidence window does not cover the card')
        require(isinstance(proof.get('frames'), list) and bool(proof['frames']), 'Review frame evidence is required')
        for frame in proof['frames']:
            path = Path(frame).expanduser().resolve(strict=True)
            require(path.is_file() and path.read_bytes()[:3] in (b'\xff\xd8\xff', b'\x89PN'), 'Expected a local review frame (JPEG/PNG)')
            evidence[str(path)] = digest(path)
    cards.sort(key=lambda card: card['_start_us'])
    require(all(a['_end_us'] <= b['_start_us'] for a, b in zip(cards, cards[1:])), 'Cards overlap one another')
    validate_character_review(plan, cards)
    return cards, evidence


def native_fade(plan, data, evidence):
    option = plan.get('native_fade_in')
    if option is None:
        return None
    require(isinstance(option, dict) and isinstance(option.get('review'), str) and option['review'].strip(),
            'Native fade requires a review of an existing local entry animation')
    ident = option.get('material_id')
    material = next((m for m in data['materials'].get('material_animations', []) if m.get('id') == ident), None)
    require(material and len(material.get('animations', [])) == 1 and
            material['animations'][0].get('type') == 'in', 'Reuse one existing native entry animation; never invent effect IDs')
    source = next((s for t in data['tracks'] if t.get('type') == 'text' for s in t.get('segments', [])
                   if s.get('id') == option.get('source_segment_id')), None)
    require(source and ident in source.get('extra_material_refs', []), 'Native fade must already belong to the reviewed source text segment')
    root = Path(material['animations'][0]['path']).expanduser().resolve(strict=True)
    require(root.is_dir() and isinstance(option.get('files'), list) and option['files'], 'List reviewed native fade resource files')
    for name in option['files']:
        path = Path(name).expanduser().resolve(strict=True)
        require(path.is_file() and path.is_relative_to(root), 'Fade evidence must stay inside its existing local resource')
        evidence[str(path)] = digest(path)
    return ident


def attach_fade(segment, ident, data):
    if ident is None:
        return
    animations = {m['id'] for m in data['materials'].get('material_animations', [])}
    refs = segment.setdefault('extra_material_refs', [])
    require(not (set(refs) & (animations-{ident})), 'Preserve the different existing text animation; review it separately')
    if ident not in refs:
        refs.append(ident)


def effective_restyle_plan(plan, data, state):
    """Use current text/timing/layout, so a saved manual edit is not reverted."""
    result = copy.deepcopy(plan)
    materials = {m['id']: m for m in data['materials'].get('texts', []) if m['id'] in state['materials']}
    segments = {s['material_id']: s for t in data['tracks'] if t['id'] in state['tracks'] for s in t['segments']}
    for card in result['cards']:
        main_id = identity(data['id'], card['id']+'/title')
        role_id = identity(data['id'], card['id']+'/detail')
        if main_id not in materials:
            continue
        segment = segments[main_id]
        timerange = segment['target_timerange']
        card.update(start=timerange['start']/1e6, duration=timerange['duration']/1e6,
                    **segment['clip']['transform'])
        if not card.get('replace_text', False):
            card['title'] = json.loads(materials[main_id]['content'])['text']
            card['detail'] = json.loads(materials[role_id]['content'])['text'] if role_id in materials else card.get('detail', '')
        if role_id in materials:
            require(segments[role_id]['target_timerange'] == timerange,
                    'Title and role have different saved timing; review separately')
    return result


def restyle_result(original, state, cards, font, fade):
    result = copy.deepcopy(original)
    materials = {m['id']: m for m in result['materials']['texts'] if m['id'] in state['materials']}
    tracks = {t['id']: t for t in result['tracks'] if t['id'] in state['tracks']}
    segments = {s['material_id']: s for t in tracks.values() for s in t['segments']}
    all_ids = {m.get('id') for values in result['materials'].values() if isinstance(values, list) for m in values if isinstance(m, dict)}
    for detail in (False, True):
        track_id = identity(original['id'], 'track/detail' if detail else 'track/main')
        for card in cards:
            if detail and not card.get('detail'):
                continue
            generated, segment = make_text(original['id'], card, detail, font, float(original['fps']))
            ident = generated['id']
            if ident in materials:
                material = materials[ident]
                content, wanted = json.loads(material['content']), json.loads(generated['content'])
                if content['text'] != wanted['text']:
                    require(card.get('replace_text') is True and len(content['styles']) == 1,
                            'Replacing rich text needs separate review')
                    content['text'] = wanted['text']
                    content['styles'][0]['range'] = [0, len(wanted['text'])]
                    material['name'] = generated['name']
                for style in content['styles']:
                    for key in ('fill', 'font', 'size'):
                        style[key] = copy.deepcopy(wanted['styles'][0][key])
                material['content'] = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
                for key in ('font_path', 'font_name', 'font_title', 'font_size', 'font_id', 'font_resource_id',
                            'font_url', 'fonts', 'text_color', 'letter_spacing'):
                    material[key] = generated[key]
                for key in ('font_team_id', 'font_third_resource_id', 'font_category_id', 'font_category_name'):
                    if key in material:
                        material[key] = ''
                if 'font_source_platform' in material:
                    material['font_source_platform'] = 0
                # Keep all saved keyframes, transforms, ranges, defaults, effects and other rich-text fields.
                segment = segments[ident]
            else:
                require(ident not in all_ids, 'New restyle material ID collides with user data')
                if not detail:
                    existing_main = tracks.get(track_id, {}).get('segments', [])
                    left, right = segment['target_timerange']['start'], segment['target_timerange']['start']+segment['target_timerange']['duration']
                    require(all(right <= s['target_timerange']['start'] or left >=
                                s['target_timerange']['start']+s['target_timerange']['duration'] for s in existing_main),
                            'New character/title overlaps an existing owned card omitted from the plan')
                all_ids.add(ident)
                if track_id not in tracks:
                    require(not any(t['id'] == track_id for t in result['tracks']), 'Restyle track ID collision')
                    track = dict(id=track_id, type='text', name='Cinematic Cards · Detail' if detail else 'Cinematic Cards · Main',
                                 flag=0, attribute=0, is_default_name=False, segments=[])
                    result['tracks'].append(track); tracks[track_id] = track
                segment['track_render_index'] = result['tracks'].index(tracks[track_id])
                entries = tracks[track_id]['segments']
                index = next((i for i, s in enumerate(entries) if s['target_timerange']['start'] >
                              segment['target_timerange']['start']), len(entries))
                entries.insert(index, segment)
                result['materials']['texts'].append(generated); materials[ident] = generated
            attach_fade(segment, fade, original)
    updated = copy.deepcopy(state)
    updated.update(tracks={i: object_hash(t) for i, t in tracks.items()},
                   materials={i: object_hash(m) for i, m in materials.items()})
    return result, updated


def stage(project, plan, out, font, preserve_owned=False):
    project, active, original, paths, signature = load(project)
    out, font = Path(out).expanduser().resolve(), Path(font).expanduser().resolve()
    require(not out.is_relative_to(project), 'Stage/backup folder must be outside the CapCut project')
    require(not out.exists(), 'Stage folder already exists; use a fresh run directory')
    old_state = read(project/STATE) if (project/STATE).exists() else None
    saved_state = old_state
    if preserve_owned:
        saved_state = reviewed_state(original, old_state, signature, digest(project/STATE), plan)
        plan = effective_restyle_plan(plan, original, saved_state)
    cards, evidence = validate_plan(plan, original, signature, font)
    fade = native_fade(plan, original, evidence)
    from media import flatten
    for source in flatten(original, project)['sources']:
        if any(source['start'] < c['evidence']['end'] and source['end'] > c['evidence']['start'] for c in cards):
            path = Path(source['path']).resolve(strict=True)
            require(path.is_file(), 'Reviewed source is not a readable file')
            evidence[str(path)] = digest(path)
    for card in cards:
        for name in card['evidence'].get('files', []):
            path = Path(name).expanduser().resolve(strict=True)
            require(path.is_file(), 'Additional evidence must be a local file')
            evidence[str(path)] = digest(path)
    base = strip_owned(original, saved_state)
    if preserve_owned:
        result, state = restyle_result(original, saved_state, cards, font, fade)
        require(strip_owned(result, state) == base, 'Restyle changed unowned project data')
        return write_stage(project, active, original, paths, signature, plan, out, result, state, base, evidence)
    result = copy.deepcopy(base)
    result['materials'].setdefault('texts', [])
    new_tracks, new_materials = [], []
    all_ids = {m.get('id') for values in result['materials'].values() if isinstance(values, list) for m in values if isinstance(m, dict)}
    for detail in (False, True):
        segments = []
        for card in cards:
            if detail and not card.get('detail'):
                continue
            material, segment = make_text(original.get('id', 'project'), card, detail, font, float(original['fps']))
            attach_fade(segment, fade, original)
            require(material['id'] not in all_ids, 'Generated material id collides with existing user material')
            all_ids.add(material['id'])
            segment['track_render_index'] = len(result['tracks'])
            result['materials']['texts'].append(material)
            new_materials.append(material)
            segments.append(segment)
        if segments:
            track = dict(id=identity(original.get('id', 'project'), 'track/detail' if detail else 'track/main'),
                         type='text', name='Cinematic Cards · Detail' if detail else 'Cinematic Cards · Main',
                         flag=0, attribute=0, is_default_name=False, segments=segments)
            require(all(track['id'] != t.get('id') for t in result['tracks']), 'Generated track id collides with user track')
            result['tracks'].append(track)
            new_tracks.append(track)
    state = dict(version=1, project_id=original.get('id'), texts_container_created='texts' not in base['materials'], tracks={t['id']: object_hash(t) for t in new_tracks},
                 materials={m['id']: object_hash(m) for m in new_materials})
    require(strip_owned(result, state) == base, 'Integrity check: original project changed while building titles')
    return write_stage(project, active, original, paths, signature, plan, out, result, state, base, evidence)


def write_stage(project, active, original, paths, signature, plan, out, result, state, base, evidence):
    out.mkdir(parents=True)
    before = {}
    for relative in paths + [STATE]:
        source = project/relative
        require(not source.is_symlink(), 'Symlinked ownership state is not supported')
        before[relative] = digest(source)
        if source.exists():
            target = out/'before'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            require(digest(target) == before[relative], 'Source changed while snapshotting')
    require(digest(active) == signature, 'Project changed while staging')
    for relative, expected in before.items():
        require(digest(project/relative) == expected, 'Project changed while staging')
    (out/'draft.json').write_bytes(encoded(result))
    (out/'state.json').write_bytes(encoded(state))
    (out/'plan.json').write_bytes(encoded(plan))
    after = {relative: digest(out/('state.json' if relative == STATE else 'draft.json')) for relative in before}
    meta = dict(version=1, project=str(project), before=before, after=after, evidence=evidence,
                base_hash=object_hash(base), plan_hash=digest(out/'plan.json'))
    (out/'transaction.json').write_bytes(encoded(meta))
    return out


def editor_running():
    if sys.platform == 'win32':
        result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, check=True)
        return bool(re.search(r'^"(?:CapCut|JianyingPro)\.exe"', result.stdout, re.I | re.M))
    result = subprocess.run(['ps', '-axo', 'comm='], capture_output=True, text=True, check=True)
    return any(Path(line.strip()).name.lower() in ('capcut', 'capcut.exe', 'jianyingpro', 'jianyingpro.exe') for line in result.stdout.splitlines())


def transaction(directory):
    directory = Path(directory).expanduser().resolve(strict=True)
    meta = read(directory/'transaction.json')
    require(meta.get('version') == 1, 'Unsupported transaction version')
    project = Path(meta['project']).resolve(strict=True)
    for relative in meta['before']:
        parts = Path(relative).parts
        allowed = relative == STATE or ((len(parts) == 1 or (len(parts) == 3 and parts[0] == 'Timelines')) and parts[-1] in ('draft_info.json', 'draft_info.json.bak', 'template-2.tmp'))
        require(allowed and not Path(relative).is_absolute() and '..' not in parts and (project/relative).resolve().is_relative_to(project), 'Unsafe transaction path')
        require(not (project/relative).is_symlink(), 'Symlinked transaction target')
        require(relative in meta['after'], 'Incomplete transaction')
        require(digest(directory/('state.json' if relative == STATE else 'draft.json')) == meta['after'][relative], 'Staged file changed: integrity check failed')
        if meta['before'][relative] is not None:
            require(digest(directory/'before'/relative) == meta['before'][relative], 'Backup changed: integrity check failed')
    require(set(meta['before']) == set(meta['after']), 'Transaction paths changed')
    require(digest(directory/'plan.json') == meta['plan_hash'], 'Staged plan changed')
    return directory, project, meta


def atomic(path, raw):
    temp = path.with_name(path.name + '.cards.part')
    with temp.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextlib.contextmanager
def locked(project):
    path = project/'.capcut-cards.lock'
    try:
        with path.open('x') as handle:
            handle.write(str(os.getpid()))
    except FileExistsError as exc:
        raise ValueError('Another card transaction holds .capcut-cards.lock; inspect its process before recovery') from exc
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def verify(directory):
    directory, project, meta = transaction(directory)
    for relative, expected in meta['after'].items():
        require(digest(project/relative) == expected, f'Output changed: {relative}')
    data, state = read(directory/'draft.json'), read(directory/'state.json')
    require(object_hash(strip_owned(data, state)) == meta['base_hash'], 'Original tracks/materials failed preservation check')
    return dict(verified=True, project=str(project), file_verification_only=True, editor_render_verified=False)


def apply(directory):
    directory, project, meta = transaction(directory)
    require(not editor_running(), 'CapCut is running: stage is ready; save and quit the application before apply '
            '(closing its window may leave it running; on macOS use Cmd+Q)')
    for name, expected in meta['evidence'].items():
        require(digest(name) == expected, 'Reviewed evidence or font changed; review and stage again')
    if all(digest(project/name) == expected for name, expected in meta['after'].items()):
        return verify(directory)
    with locked(project):
        for name, expected in meta['before'].items():
            require(digest(project/name) == expected, f'Project changed since staging: {name}')
        written = []
        try:
            for name in meta['before']:
                require(not editor_running(), 'CapCut started during apply; rolling back')
                require(digest(project/name) == meta['before'][name], 'Project changed during apply')
                atomic(project/name, (directory/('state.json' if name == STATE else 'draft.json')).read_bytes())
                written.append(name)
            return verify(directory)
        except BaseException:
            for name in reversed(written):
                if digest(project/name) == meta['after'][name]:
                    if meta['before'][name] is None:
                        (project/name).unlink()
                    else:
                        atomic(project/name, (directory/'before'/name).read_bytes())
            raise


def restore(directory):
    directory, project, meta = transaction(directory)
    require(not editor_running(), 'CapCut is running; save and close before restore')
    with locked(project):
        for name in meta['before']:
            require(digest(project/name) in (meta['before'][name], meta['after'][name]), f'Project changed after cards: {name}; refusing to overwrite user edits')
        for name, expected in meta['before'].items():
            require(not editor_running(), 'CapCut started during restore; stop and resume safely after closing')
            require(digest(project/name) in (expected, meta['after'][name]), 'Project changed during restore; preserve user edits')
            if digest(project/name) == expected:
                continue
            if expected is None:
                (project/name).unlink()
            else:
                atomic(project/name, (directory/'before'/name).read_bytes())
        require(all(digest(project/name) == expected for name, expected in meta['before'].items()), 'Restore verification failed')
    return dict(restored=True, project=str(project))


def project_roots():
    home = Path.home()
    roots = [home/'Movies/CapCut/User Data/Projects/com.lveditor.draft']
    for variable in ('LOCALAPPDATA', 'APPDATA'):
        if os.environ.get(variable):
            roots.append(Path(os.environ[variable])/'CapCut/User Data/Projects/com.lveditor.draft')
    return roots


def resolve(value):
    path = Path(value).expanduser()
    if path.is_dir():
        return path.resolve()
    matches = [root/value for root in project_roots() if (root/value/'draft_info.json').is_file()]
    require(len(matches) == 1, 'Project name missing or ambiguous; use its exact local folder path')
    return matches[0]


def choose_font():
    candidates = [Path('/System/Library/Fonts/Supplemental/Baskerville.ttc'),
                  Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/georgia.ttf',
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'),
                  Path('/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf')]
    return next((path for path in candidates if path.is_file()), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('projects', help='List local project names/paths without opening CapCut')
    view = sub.add_parser('inspect', help='Read active timeline, nested sources and transitions')
    view.add_argument('project')
    probe_parser = sub.add_parser('probe', help='Extract bounded source frames/audio, never alter original media')
    probe_parser.add_argument('project'); probe_parser.add_argument('--at', type=float, required=True)
    probe_parser.add_argument('--before', type=float, default=4); probe_parser.add_argument('--after', type=float, default=5)
    probe_parser.add_argument('--out', type=Path, required=True)
    for command, help_text in [('stage', 'Compile reviewed card plan with backups; no project writes'),
                               ('restyle', 'Preserve saved owned titles and restyle/add reviewed cards')]:
        build = sub.add_parser(command, help=help_text)
        build.add_argument('project'); build.add_argument('--plan', type=Path, required=True); build.add_argument('--out', type=Path, required=True)
        build.add_argument('--font', type=Path, default=choose_font())
    for command in ('apply', 'verify', 'restore'):
        item = sub.add_parser(command); item.add_argument('stage', type=Path)
    args = parser.parse_args()
    if args.command == 'projects':
        output = [{'name': p.name, 'path': str(p)} for root in project_roots() if root.is_dir() for p in root.iterdir() if (p/'draft_info.json').is_file()]
    elif args.command == 'inspect':
        output = inspect(resolve(args.project))
    elif args.command == 'probe':
        from media import probe
        output = probe(inspect(resolve(args.project)), args.at, args.before, args.after, args.out)
    elif args.command in ('stage', 'restyle'):
        require(args.font is not None, 'No local serif font found; provide --font with an installed TTF/OTF/TTC')
        output = {'stage': str(stage(resolve(args.project), read(args.plan), args.out, args.font,
                                    preserve_owned=args.command == 'restyle')), 'applied': False}
    else:
        output = globals()[args.command](args.stage)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
