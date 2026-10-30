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

from native_text import identity, make_text, apply_text_layout
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
        owned_animations = state.get('animations', {})
        require(not any(set(s.get('extra_material_refs', [])) & set(owned_animations)
                        for t in base['tracks'] for s in t.get('segments', [])),
                'Owned animation is now referenced by unowned user data; preserve the shared resource')
        animations = base['materials'].get('material_animations', [])
        found = {item['id']: item for item in animations if item.get('id') in owned_animations}
        require(set(found) == set(owned_animations) and
                all(object_hash(found[i]) == h for i, h in owned_animations.items()),
                'Owned native animations changed; preserve those edits')
        animations[:] = [item for item in animations if item.get('id') not in owned_animations]
        if state.get('animations_container_created'):
            require(not animations, 'New unowned animation found in created animation collection')
            base['materials'].pop('material_animations', None)
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
    collections = [('tracks', data['tracks']), ('materials', data['materials'].get('texts', []))]
    if state.get('animations'):
        collections.append(('animations', data['materials'].get('material_animations', [])))
    for key, values in collections:
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
                    ('project_sha256', 'state_sha256', 'tracks', 'materials') +
                    (('animations',) if state.get('animations') else ())),
                'Ownership review is stale or incomplete; inspect and review again')
    updated = copy.deepcopy(state)
    updated.update(tracks=report['tracks'], materials=report['materials'])
    if state.get('animations'):
        updated['animations'] = report['animations']
    if any(m.get('id') not in state.get('animations', {}) for m in data['materials'].get('material_animations', [])):
        updated['animations_container_created'] = False
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


def box(value):
    require(isinstance(value, list) and len(value) == 4, 'Reviewed bounds need [left, bottom, right, top]')
    x1, y1, x2, y2 = [number(v, 'bounds') for v in value]
    require(-.9 <= x1 < x2 <= .9 and -.9 <= y1 < y2 <= .9, 'Reviewed bounds leave the frame safe area')
    return value


def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def overlaps(a, b):
    return a['_start_us'] < b['_end_us'] and b['_start_us'] < a['_end_us']


def validate_layouts(cards, plan):
    groups = {}
    for card in cards:
        bounds = card.get('bounds')
        if bounds is not None:
            box(bounds)
            require(card['evidence'].get('layout_review'), 'Record full-hold layout_review for reviewed bounds')
            layout = card.get('layout', 'lower-left')
            options = card.get('text_layout', {})
            x = card.get('x', -.52 if layout == 'lower-left' else 0.)
            y = card.get('y', -.66 if layout == 'lower-left' else .035)
            for role in ('title', 'detail') if card.get('detail') else ('title',):
                saved = card.get('_saved_positions', {}).get(role, {})
                ax = options.get(role+'_x', saved.get('x', x))
                ay = options.get(role+'_y', saved.get('y', y-(.13 if role == 'detail' else 0.)))
                require(bounds[0] <= ax <= bounds[2] and bounds[1] <= ay <= bounds[3],
                        'Declared bounds do not contain the '+role+' anchor; bounds are not a native text measurement')
            for zone in card.get('exclusion_zones', []):
                require(not intersects(bounds, box(zone)), 'Card bounds collide with a subtitle/face/gesture exclusion zone')
        group = card.get('simultaneous_group')
        if group is not None:
            require(isinstance(group, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', group), 'Invalid simultaneous group')
            require(card.get('kind') == 'character' and len(card.get('characters', [])) == 1,
                    'Simultaneous groups need one confirmed person per label')
            require(bounds is not None and card['evidence'].get('identity_association') and
                    card['evidence'].get('layout_review'), 'Simultaneous labels need reviewed bounds, layout and identity_association')
            require(plan.get('introduce_characters') is True, 'Simultaneous labels require the principal review ledger')
            groups.setdefault(group, []).append(card)
    for members in groups.values():
        require(len(members) >= 2, 'A simultaneous group needs at least two independent labels')
        first = members[0]
        require(all((c['_start_us'], c['_end_us'], c['_style']['fade_seconds']) ==
                    (first['_start_us'], first['_end_us'], first['_style']['fade_seconds']) for c in members),
                'Simultaneous labels must share timing and fades')
    for i, a in enumerate(cards):
        for b in cards[i+1:]:
            if not overlaps(a, b):
                continue
            require(a.get('simultaneous_group') and a.get('simultaneous_group') == b.get('simultaneous_group'),
                    'Cards overlap outside a reviewed simultaneous group')
            require(not intersects(a['bounds'], b['bounds']), 'Simultaneous label bounds collide')


def track_identity(project_id, card, detail):
    role = 'track/detail' if detail else 'track/main'
    if card.get('simultaneous_group'):
        role += '/' + card['id']
    return identity(project_id, role)


def review_manifest(card, left, right, signature, evidence, sources):
    """Bind selected frames to real probe times; this does not recognize people."""
    proof = card['evidence']
    if not proof.get('manifest'):
        return
    path = Path(proof['manifest']).expanduser().resolve(strict=True)
    manifest = read(path)
    require(manifest.get('project_sha256') == signature, 'Frame manifest belongs to a different project revision')
    entries = {str(Path(f['file']).resolve()): f for f in manifest.get('frames', [])}
    moving = [s for s in sources if s['kind'] == 'videos' and s.get('source_type') != 'photo']
    def usable(frame):
        at = number(frame.get('timeline_time'), 'frame timeline time')
        return frame.get('source_type') != 'photo' or not any(s['start'] <= at < s['end'] for s in moving)
    selected = []
    for name in proof['frames']:
        frame = entries.get(str(Path(name).resolve()))
        require(frame is not None, 'Review frame is absent from its manifest')
        if usable(frame):
            selected.append(number(frame.get('timeline_time'), 'frame timeline time'))
    # Probe samples every half second, plus source boundaries. Samples must reach
    # both ends and leave no unsampled interval longer than that cadence.
    times = sorted(set(t for t in selected if left-.51 <= t <= right+.51))
    require(times and times[0] <= left+.51 and times[-1] >= right-.51 and
            all(b-a <= .51 for a, b in zip(times, times[1:])),
            'Selected frame coverage does not cover the full card hold; include cut-adjacent and end frames')
    if card.get('kind') == 'character':
        selected_files = {str(Path(f).resolve()) for f in proof['frames']}
        for cut in manifest.get('cuts', []):
            at = number(cut['timeline_time'], 'cut timeline time')
            if not left < at < right:
                continue
            reviews = [r for r in proof.get('cut_continuity', []) if abs(number(r.get('at'), 'reviewed cut')-at) < .02]
            require(len(reviews) == 1, 'Character hold crosses a cut without a unique identity continuity review; end before it or review both shots')
            review = reviews[0]
            require(card.get('characters') and set(card['characters']) <= set(review.get('characters', [])) and
                    isinstance(review.get('review'), str) and review['review'].strip(),
                    'Cut continuity must confirm the same principal IDs on both sides')
            for side in ('before', 'after'):
                name = str(Path(review.get(side, '')).resolve())
                frame = entries.get(name)
                require(name in selected_files and frame and usable(frame),
                        'Cut continuity needs selected footage frames on both sides, not a static overlay')
                delta = at-number(frame['timeline_time'], 'cut frame time')
                require((0 < delta <= .15) if side == 'before' else (-.15 <= delta < 0),
                        'Cut continuity frame must be immediately '+side+' the cut')
    evidence[str(path)] = digest(path)


def validate_plan(plan, data, signature, font, sources):
    require(plan.get('version') in (1, 2), 'Plan version must be 1 or 2')
    require(plan.get('project_sha256') == signature, 'Project changed; regenerate the plan from current inspection')
    cards = copy.deepcopy(plan.get('cards', []))
    require(isinstance(cards, list) and cards, 'Choose at least one necessary card; otherwise leave the project unchanged')
    requirements = plan.get('requirements', {})
    require(isinstance(requirements, dict) and not set(requirements)-{'ending', 'native_fade'} and
            all(isinstance(v, bool) for v in requirements.values()), 'Unsupported task requirements')
    require(not requirements.get('ending') or any(c.get('kind') == 'ending' for c in cards),
            'The task requires an ending card')
    require(not requirements.get('native_fade') or plan.get('native_fade_in'),
            'The task requires native fade; opacity keyframes alone do not satisfy it')
    fps = float(data['fps'])
    evidence = {}
    ids = set()
    protected = plan.get('protected_ranges', [])
    require(isinstance(protected, list), 'protected_ranges must be a list')
    for interval in protected:
        start, end = number(interval['start'], 'protected start'), number(interval['end'], 'protected end')
        require(0 <= start < end <= data['duration']/1e6 and interval.get('reason'), 'Invalid protected range')
    for card in cards:
        require(card.get('kind', 'time-location') in ('time', 'location', 'time-location', 'character', 'ending'), 'Unknown card kind')
        selected_font = card.get('font') or plan.get('font') or font or card.get('_inherited_font') or choose_font()
        require(selected_font is not None, 'Choose an installed font with --font, plan.font or card.font')
        selected_font = Path(selected_font).expanduser().resolve()
        require(selected_font.is_file() and selected_font.read_bytes()[:4] in
                (b'\x00\x01\x00\x00', b'OTTO', b'ttcf', b'true'), 'Readable local TTF/OTF/TTC font required')
        card['_font'] = str(selected_font)
        card['_font_override'] = bool(card.get('font') or plan.get('font') or font)
        evidence[str(selected_font)] = digest(selected_font)
        selected_style = {**plan.get('style', {}), **card.get('style', {})}
        card['_style_overrides'] = list(selected_style) if 'theme' not in selected_style else [
            'title_color', 'detail_color', 'title_size', 'detail_size', 'title_spacing', 'detail_spacing', 'fade_seconds']
        text_layout = card.get('text_layout', {})
        require(isinstance(text_layout, dict) and not set(text_layout)-{'scale', 'line_max_width', 'fixed_width', 'title_x', 'title_y', 'detail_x', 'detail_y'},
                'Unsupported text_layout option')
        for key in ('title_x', 'title_y', 'detail_x', 'detail_y'):
            if key in text_layout:
                require(-.82 <= number(text_layout[key], key) <= .82 and card.get('bounds') is not None and
                        card.get('evidence', {}).get('layout_review'), 'Position repair needs reviewed bounds and layout_review')
        for key, low, high in [('scale', .1, 4), ('line_max_width', .05, .9), ('fixed_width', 1, 10000)]:
            if key in text_layout:
                require(low <= number(text_layout[key], key) <= high, 'Invalid native text_layout '+key)

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
        for key, limit in [('title', 96), ('detail', 128)]:
            text = card.get(key, '')
            require(isinstance(text, str) and len(text) <= limit and
                    all(ord(ch) >= 32 or ch == '\n' for ch in text) and
                    (not text or (len(text.split('\n')) <= 2 and all(line.strip() for line in text.split('\n')))),
                    f'Use a concise {key}, at most two nonempty lines')
        require(bool(card['title'].strip()), 'Card title is blank')
        start = number(card['start'], 'start')
        duration = number(card.get('duration', 3.2), 'duration')
        minimum = 2.0 if card.get('kind') == 'character' else 2.8
        proof = card.get('evidence', {})
        short_review = proof.get('short_hold_review') if isinstance(proof, dict) else None
        reviewed_short = (plan['version'] == 2 and 0 < duration < minimum and
                          isinstance(short_review, str) and bool(short_review.strip()))
        require((0 < duration if card.get('_saved_hold') else minimum <= duration <= 8 or reviewed_short),
                'Allow reading time: normally character 2–8 seconds, other cards 2.8–8; a shorter new hold needs version2 and explicit short_hold_review')
        card['_start_us'] = round(round(start*fps)*1e6/fps)
        card['_end_us'] = round(round((start+duration)*fps)*1e6/fps)
        left, right = card['_start_us']/1e6, card['_end_us']/1e6
        require(0 <= left < right <= data['duration']/1e6, 'Card falls outside project duration')
        if reviewed_short and not card.get('_saved_hold'):
            require(round((right-left)*fps) >= 10, 'Short hold cannot fit the distinct opacity keyframes; this is a technical limit, not a reading-time approval')
        require(card.get('layout', 'lower-left') in ('lower-left', 'center'), 'Unknown layout')
        for key, default in [('x', -.52), ('y', -.66)]:
            require(-.82 <= number(card.get(key, default), key) <= .82, 'Keep text within the frame safe area')
        default_y = -.66 if card.get('layout', 'lower-left') == 'lower-left' else .035
        detail_y = text_layout.get('detail_y', card.get('_saved_positions', {}).get('detail', {}).get(
            'y', card.get('y', default_y)-.13))
        require(not card.get('detail') or -.82 <= detail_y <= .82, 'Detail text falls outside the safe area')
        for interval in protected:
            if card.get('kind') == 'character' and interval.get('kind') == 'dialogue':
                continue
            require(right <= interval['start']-.15 or left >= interval['end']+.15, f'Card overlaps protected dialogue/reaction: {interval["reason"]}')
        proof = card.get('evidence', {})
        require(isinstance(proof, dict) and proof.get('visual_review') and proof.get('dialogue_review'), 'Review actual images and dialogue, recording findings')
        if plan['version'] == 2:
            require(proof.get('manifest') and card.get('bounds') and proof.get('layout_review'),
                    'New plans require a probe manifest and reviewed full-label bounds')
        if card.get('kind') == 'character':
            require(plan['version'] == 1 or card.get('characters'), 'New character plans need principal IDs for independent identity review')
            require(proof.get('character_identity') and proof.get('first_appearance'), 'Character identity and first appearance must be reviewed; do not invent a name from a face')
            omission = proof.get('role_omission_reason')
            require(card.get('detail', '').strip() or (isinstance(omission, str) and omission.strip()), 'Character role required in detail; document role_omission_reason for names-only requests, unknown roles or spoilers')
        require(number(proof.get('start'), 'review start') <= left and number(proof.get('end'), 'review end') >= right, 'Evidence window does not cover the card')
        require(isinstance(proof.get('frames'), list) and bool(proof['frames']), 'Review frame evidence is required')
        review_manifest(card, left, right, signature, evidence, sources)
        for frame in proof['frames']:
            path = Path(frame).expanduser().resolve(strict=True)
            require(path.is_file() and path.read_bytes()[:3] in (b'\xff\xd8\xff', b'\x89PN'), 'Expected a local review frame (JPEG/PNG)')
            evidence[str(path)] = digest(path)
    cards.sort(key=lambda card: card['_start_us'])
    validate_layouts(cards, plan)
    validate_character_review(plan, cards)
    return cards, evidence


def native_fade(plan, data, evidence):
    option = plan.get('native_fade_in')
    if option is None:
        return None
    require(isinstance(option, dict) and isinstance(option.get('review'), str) and option['review'].strip(),
            'Native fade requires a review of an existing local entry animation')
    external = option.get('source_project')
    source_data = data
    if external:
        _, source_file, source_data, _, source_hash = load(external)
        require(option.get('source_project_sha256') == source_hash,
                'Native template project changed; inspect and review its current revision')
        evidence[str(source_file)] = source_hash
    ident = option.get('material_id')
    material = next((m for m in source_data['materials'].get('material_animations', []) if m.get('id') == ident), None)
    animations = material.get('animations', []) if material else []
    types = [a.get('type') for a in animations]
    require(material and (types == ['in'] or len(types) == 2 and set(types) == {'in', 'out'}),
            'Reuse an existing native entry or in/out pair; never invent effect IDs')
    source = next((s for t in source_data['tracks'] if t.get('type') == 'text' for s in t.get('segments', [])
                   if s.get('id') == option.get('source_segment_id')), None)
    require(source and ident in source.get('extra_material_refs', []), 'Native fade must already belong to the reviewed source text segment')
    roots = [Path(a['path']).expanduser().resolve(strict=True) for a in animations]
    require(all(root.is_dir() for root in roots) and isinstance(option.get('files'), list) and option['files'],
            'List reviewed native fade resource files')
    covered = set()
    for name in option['files']:
        path = Path(name).expanduser().resolve(strict=True)
        matches = {root for root in roots if path.is_relative_to(root)}
        require(path.is_file() and matches, 'Fade evidence must stay inside its existing local resource')
        covered.update(matches)
        evidence[str(path)] = digest(path)
    require(covered == set(roots), 'Pin resource files for both native fade directions')
    durations = option.get('durations_seconds')
    if durations is not None:
        require(isinstance(durations, dict) and durations and not set(durations)-set(types),
                'Native fade durations must name existing in/out directions')
        durations = {kind: round(number(value, 'native fade seconds')*1000000)
                     for kind, value in durations.items()}
        require(all(value > 0 for value in durations.values()), 'Native fade durations must be positive')
    if external or durations is not None:
        imported = copy.deepcopy(material)
        suffix = '/'+object_hash(durations) if durations is not None else ''
        imported['id'] = identity(data['id'], 'native-animation/'+source_data['id']+'/'+ident+suffix)
        for animation in imported['animations']:
            if durations is not None and animation['type'] in durations:
                animation['duration'] = durations[animation['type']]
        return {'material': imported}
    return ident


def attach_fade(segment, ident, data):
    if ident is None:
        return
    if isinstance(ident, dict):
        ident = ident['material']['id']
    animations = {m['id'] for m in data['materials'].get('material_animations', [])}
    refs = segment.setdefault('extra_material_refs', [])
    require(not (set(refs) & (animations-{ident})), 'Preserve the different existing text animation; review it separately')
    if ident not in refs:
        refs.append(ident)


def import_fade(result, state, fade):
    if not isinstance(fade, dict):
        return
    material = fade['material']
    created = 'material_animations' not in result['materials']
    animations = result['materials'].setdefault('material_animations', [])
    existing = next((m for m in animations if m.get('id') == material['id']), None)
    if existing:
        require(existing == material, 'Imported native animation ID collides with existing animation data')
        return
    animations.append(copy.deepcopy(material))
    state.setdefault('animations', {})[material['id']] = object_hash(material)
    if created:
        state['animations_container_created'] = True


def subtitle_template(data, plan, evidence):
    option = plan.get('subtitle_template')
    if option is None:
        return data, []
    require(isinstance(option, dict) and isinstance(option.get('review'), str) and option['review'].strip(),
            'Subtitle appearance needs a reviewed native template')
    project, source, template_data, _, signature = load(option['source_project'])
    require(option.get('source_project_sha256') == signature, 'Subtitle template changed; inspect and review again')
    evidence[str(source)] = signature
    material = next((copy.deepcopy(m) for m in template_data['materials'].get('texts', [])
                     if m.get('id') == option.get('material_id') and m.get('type') == 'subtitle'), None)
    require(material is not None, 'Choose an existing native subtitle material as the appearance template')
    content = json.loads(material['content'])
    fonts = [material] + [s.get('font', {}) for s in content.get('styles', [])]
    for font in fonts:
        key = 'font_path' if font is material else 'path'
        if not font.get(key):
            continue
        raw = re.sub(r'^##_draftpath_placeholder_[^/\\]+_##[/\\]', '', font[key])
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = project/path
        path = path.resolve(strict=True)
        require(path.is_file() and path.read_bytes()[:4] in (b'\x00\x01\x00\x00', b'OTTO', b'ttcf', b'true'),
                'Subtitle template font must be a readable local font')
        font[key] = str(path)
        evidence[str(path)] = digest(path)
    material['content'] = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
    y, columns = option.get('y'), option.get('wrap_columns')
    require(y is None or -.85 <= number(y, 'subtitle y') <= .8, 'Subtitle y outside the reviewed canvas')
    require(columns is None or isinstance(columns, int) and not isinstance(columns, bool) and 8 <= columns <= 120,
            'Choose a readable subtitle wrap width')
    positions = option.get('cue_positions', [])
    require(isinstance(positions, list), 'Subtitle cue_positions must be a reviewed list')
    reviewed = {}
    for position in positions:
        require(isinstance(position, dict) and not set(position)-{'segment_id', 'x', 'y', 'wrap_columns', 'review'},
                'Unsupported subtitle cue position fields')
        ident = position.get('segment_id')
        require(isinstance(ident, str) and ident and isinstance(position.get('review'), str) and position['review'].strip(),
                'Subtitle cue position needs an exact segment ID and whole-cue review')
        require(ident not in reviewed, 'Duplicate subtitle cue position')
        require('x' in position or 'y' in position, 'Choose a subtitle cue position')
        for axis in ('x', 'y'):
            if axis in position:
                require(-.85 <= number(position[axis], 'subtitle cue '+axis) <= .8,
                        'Subtitle cue position outside the reviewed canvas')
        if 'wrap_columns' in position:
            width = position['wrap_columns']
            require(isinstance(width, int) and not isinstance(width, bool) and 8 <= width <= 120,
                    'Choose a readable subtitle cue wrap width')
        reviewed[ident] = position
    from native_text import restyle_subtitles
    return restyle_subtitles(data, material, y, columns, reviewed)


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
        card['_inherited_font'] = materials[main_id].get('font_path')
        for mid in (main_id, role_id):
            if mid in materials:
                for st in json.loads(materials[mid]['content'])['styles']:
                    path = st.get('font', {}).get('path')
                    if path:
                        card.setdefault('evidence', {}).setdefault('files', []).append(path)
        card['_saved_positions'] = {role: copy.deepcopy(segments[mid]['clip']['transform'])
                                    for role, mid in [('title', main_id), ('detail', role_id)] if mid in materials}
        card['_saved_hold'] = True
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
    planned = {identity(original['id'], c['id']+'/title') for c in cards}
    # All owned title segments, including lanes from simultaneous introductions.
    detail_ids = {identity(original['id'], c['id']+'/detail') for c in cards}
    for card in cards:
        main_id = identity(original['id'], card['id']+'/title')
        if main_id in materials:
            continue
        for saved in segments.values():
            if saved['material_id'] in planned or saved['material_id'] in detail_ids:
                continue
            timing = saved['target_timerange']
            require(card['_end_us'] <= timing['start'] or card['_start_us'] >= timing['start']+timing['duration'],
                    'New character/title overlaps an existing owned card omitted from the plan')
    for detail in (False, True):
        for card in cards:
            if detail and not card.get('detail'):
                continue
            track_id = track_identity(original['id'], card, detail)
            generated, segment = make_text(original['id'], card, detail, Path(card['_font']), float(original['fps']))
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
                role = 'detail' if detail else 'title'
                requested = card['_style_overrides']
                for style in content['styles']:
                    for suffix, key in [('color', 'fill'), ('size', 'size'), ('spacing', 'letter_spacing')]:
                        if role+'_'+suffix in requested:
                            style[key] = copy.deepcopy(wanted['styles'][0][key] if key != 'letter_spacing' else generated[key])
                    if card['_font_override']:
                        style['font'] = copy.deepcopy(wanted['styles'][0]['font'])
                material['content'] = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
                for suffix, key in [('color', 'text_color'), ('size', 'font_size'), ('spacing', 'letter_spacing')]:
                    if role+'_'+suffix in requested:
                        material[key] = generated[key]
                if card['_font_override']:
                    for key in ('font_path', 'font_name', 'font_title', 'font_id', 'font_resource_id', 'font_url', 'fonts'):
                        material[key] = generated[key]
                for key in ('font_team_id', 'font_third_resource_id', 'font_category_id', 'font_category_name'):
                    if card['_font_override'] and key in material:
                        material[key] = ''
                if card['_font_override'] and 'font_source_platform' in material:
                    material['font_source_platform'] = 0
                # Keep all saved keyframes, transforms, ranges, defaults, effects and other rich-text fields.
                segment = segments[ident]
                apply_text_layout(material, segment, card, detail)
                if 'base_content' in material:
                    material['base_content'] = material['content']
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
    out = Path(out).expanduser().resolve()
    font = Path(font).expanduser().resolve() if font is not None else None
    require(not out.is_relative_to(project), 'Stage/backup folder must be outside the CapCut project')
    require(not out.exists(), 'Stage folder already exists; use a fresh run directory')
    old_state = read(project/STATE) if (project/STATE).exists() else None
    saved_state = old_state
    plan = copy.deepcopy(plan)
    for card in plan.get('cards', []):
        card.pop('_saved_hold', None)
        card.pop('_saved_positions', None)
    if preserve_owned:
        saved_state = reviewed_state(original, old_state, signature, digest(project/STATE), plan)
        plan = effective_restyle_plan(plan, original, saved_state)
    from media import flatten
    mapped_sources = flatten(original, project)['sources']
    cards, evidence = validate_plan(plan, original, signature, font, mapped_sources)
    fade = native_fade(plan, original, evidence)
    if fade and cards:
        material = fade['material'] if isinstance(fade, dict) else next(
            m for m in original['materials']['material_animations'] if m['id'] == fade)
        durations = [number(a.get('duration'), 'native fade duration for hold') for a in material['animations']]
        require(all(d > 0 for d in durations) and all(sum(durations) < c['_end_us']-c['_start_us'] for c in cards),
                'Native fades consume the hold; choose a readable hold/effect treatment rather than extending across an identity cut')
    working, subtitle_changes = subtitle_template(original, plan, evidence)
    if subtitle_changes:
        plan['_subtitle_changes'] = subtitle_changes
    for source in mapped_sources:
        if any(source['start'] < c['evidence']['end'] and source['end'] > c['evidence']['start'] for c in cards):
            path = Path(source['path']).resolve(strict=True)
            require(path.is_file(), 'Reviewed source is not a readable file')
            evidence[str(path)] = digest(path)
    for card in cards:
        for name in card['evidence'].get('files', []):
            path = Path(name).expanduser().resolve(strict=True)
            require(path.is_file(), 'Additional evidence must be a local file')
            evidence[str(path)] = digest(path)
    base = strip_owned(working, saved_state)
    if preserve_owned:
        result, state = restyle_result(working, saved_state, cards, font, fade)
        import_fade(result, state, fade)
        require(strip_owned(result, state) == base, 'Restyle changed unowned project data')
        return write_stage(project, active, original, paths, signature, plan, out, result, state, base, evidence)
    result = copy.deepcopy(base)
    result['materials'].setdefault('texts', [])
    new_tracks, new_materials = [], []
    all_ids = {m.get('id') for values in result['materials'].values() if isinstance(values, list) for m in values if isinstance(m, dict)}
    for detail in (False, True):
        lanes = {}
        for card in cards:
            if detail and not card.get('detail'):
                continue
            material, segment = make_text(original.get('id', 'project'), card, detail, Path(card['_font']), float(original['fps']))
            attach_fade(segment, fade, original)
            require(material['id'] not in all_ids, 'Generated material id collides with existing user material')
            all_ids.add(material['id'])
            track_id = track_identity(original['id'], card, detail)
            if track_id not in lanes:
                track = dict(id=track_id, type='text', name='Cinematic Cards · Detail' if detail else 'Cinematic Cards · Main',
                             flag=0, attribute=0, is_default_name=False, segments=[])
                require(all(track_id != t.get('id') for t in result['tracks']), 'Generated track id collides with user track')
                lanes[track_id] = track
                result['tracks'].append(track); new_tracks.append(track)
            segment['track_render_index'] = result['tracks'].index(lanes[track_id])
            lanes[track_id]['segments'].append(segment)
            result['materials']['texts'].append(material); new_materials.append(material)
    state = dict(version=1, project_id=original.get('id'), texts_container_created='texts' not in base['materials'], tracks={t['id']: object_hash(t) for t in new_tracks},
                 materials={m['id']: object_hash(m) for m in new_materials})
    import_fade(result, state, fade)
    require(strip_owned(result, state) == base, 'Integrity check: original project changed while building titles')
    return write_stage(project, active, original, paths, signature, plan, out, result, state, base, evidence)


def incremental_outputs(project, active, original, result, state, plan, evidence):
    if not plan.get('sync_incremental_snapshot'):
        return {}
    folder = active.parent/'attachment/patch'
    mini, patch = folder/'mini_draft.json', folder/'patch.json'
    require(not mini.is_symlink() and not patch.is_symlink(), 'Symlinked incremental snapshot')
    require(mini.is_file() and patch.is_file(), 'Missing reviewed incremental snapshot/patch pair')
    patch_hash = digest(patch)
    require(json.loads(patch.read_text()) in ([], {'patch_data': []}),
            'Nonempty incremental patch: save and quit CapCut; never discard user edits')
    require(digest(patch) == patch_hash, 'Incremental patch changed while staging')
    evidence[str(patch)] = patch_hash
    snapshot = read(mini)
    old_materials = {m['id']: m for m in original['materials']['texts']}
    new_materials = {m['id']: m for m in result['materials']['texts']}
    old_segments = {seg['id']: seg for t in original['tracks'] if t['id'] in state['tracks'] for seg in t['segments']}
    new_segments = {seg['id']: seg for t in result['tracks'] if t['id'] in state['tracks'] for seg in t['segments']}
    require(old_segments.keys() == new_segments.keys(), 'Incremental sync supports existing-title restyles only')
    entries = snapshot.get('mini_draft_data', {}).get('segments')
    require(isinstance(entries, list), 'Unsupported incremental snapshot schema')
    found = set()
    for entry in entries:
        ident = entry.get('id')
        if ident not in old_segments:
            continue
        require(ident not in found, 'Duplicate owned segment in incremental snapshot')
        found.add(ident)
        old = old_materials[old_segments[ident]['material_id']]
        material = entry.get('material', {})
        require(material.get('type') == 'text' and material.get('content') == old['content'],
                'Incremental snapshot differs from reviewed current card content; preserve it')
        material['content'] = new_materials[new_segments[ident]['material_id']]['content']
    require(found == set(old_segments), 'Incremental snapshot is missing owned titles')
    return {str(mini.relative_to(project)): encoded(snapshot)}


def staged_file(directory, relative):
    if Path(relative).name == 'mini_draft.json':
        return directory/'incremental-mini.json'
    return directory/('state.json' if relative == STATE else 'draft.json')


def write_stage(project, active, original, paths, signature, plan, out, result, state, base, evidence):
    auxiliary = incremental_outputs(project, active, original, result, state, plan, evidence)
    out.mkdir(parents=True)
    before = {}
    for relative in paths + [STATE] + list(auxiliary):
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
    for relative, raw in auxiliary.items():
        staged_file(out, relative).write_bytes(raw)
    after = {relative: digest(staged_file(out, relative)) for relative in before}
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
        allowed = allowed or (len(parts) == 5 and parts[0] == 'Timelines' and parts[2:] == ('attachment', 'patch', 'mini_draft.json'))
        require(allowed and not Path(relative).is_absolute() and '..' not in parts and (project/relative).resolve().is_relative_to(project), 'Unsafe transaction path')
        require(not (project/relative).is_symlink(), 'Symlinked transaction target')
        require(relative in meta['after'], 'Incomplete transaction')
        require(digest(staged_file(directory, relative)) == meta['after'][relative], 'Staged file changed: integrity check failed')
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


def visual_review_facts(directory):
    """Neutral staged facts and real frames; exclude the author's review conclusions."""
    directory, project, meta = transaction(directory)
    plan, data = read(directory/'plan.json'), read(directory/'draft.json')
    materials = {m['id']: m for m in data['materials'].get('texts', [])}
    segments = {s['material_id']: s for t in data['tracks'] for s in t.get('segments', [])}
    from media import flatten
    sources = flatten(data, project)['sources']
    moving = [s for s in sources if s['kind'] == 'videos' and s.get('source_type') != 'photo']
    photographs = [s for s in sources if s['kind'] == 'videos' and s.get('source_type') == 'photo']
    overlays = [{k: s.get(k) for k in ('id', 'path', 'start', 'end', 'review_framing')}
                for s in sources if s.get('source_type') == 'photo']
    cards = []
    for card in plan['cards']:
        proof = card['evidence']
        require(proof.get('manifest'), 'Visual bundle needs probe manifests; regenerate legacy evidence')
        manifest_path = Path(proof['manifest']).resolve(strict=True)
        require(meta['evidence'].get(str(manifest_path)) == digest(manifest_path), 'Review manifest changed')
        manifest = read(manifest_path)
        title_id = identity(data['id'], card['id']+'/title')
        segment = segments[title_id]; timerange = segment['target_timerange']
        left, right = timerange['start']/1e6, (timerange['start']+timerange['duration'])/1e6
        lines = {}
        for role in ('title', 'detail'):
            mid = identity(data['id'], card['id']+'/'+role)
            if mid in materials:
                material = materials[mid]
                lines[role] = dict(text=json.loads(material['content'])['text'],
                                   font=material.get('font_path'), size=material.get('font_size'),
                                   clip=copy.deepcopy(segments[mid]['clip']))
        frames = []
        for frame in manifest['frames']:
            at = frame['timeline_time']
            if not left-.15 <= at <= right+.15:
                continue
            photo = frame.get('source_type') == 'photo'
            if photo and any(s['start'] <= at < s['end'] for s in moving):
                continue  # A static logo/overlay cannot substitute for the active footage.
            item = {k: frame.get(k) for k in ('file', 'timeline_time', 'source', 'source_time')}
            item.update(sha256=digest(frame['file']), inside_hold=left <= at < right)
            require(item['sha256'], 'Review frame missing')
            pool = photographs if photo else moving
            if pool or photo:
                candidates = [s for s in pool if s['start'] <= at < s['end'] and
                              (s['id'] == frame.get('source_segment_id') if frame.get('source_segment_id') else
                               str(Path(s['path']).resolve()) == str(Path(frame.get('source', '')).resolve()))]
                require(len(candidates) == 1, 'Probe framing cannot be mapped uniquely; regenerate helper evidence')
                item['review_framing'] = copy.deepcopy(candidates[0]['review_framing'])
            frames.append(item)
        frames.sort(key=lambda f: (f['timeline_time'], f['file']))
        require(any(f['inside_hold'] for f in frames), 'No footage frames inside card hold')
        cards.append(dict(id=card['id'], kind=card.get('kind','time-location'),
                          characters=card.get('characters', []), start=left, end=right,
                          lines=lines, bounds=card.get('bounds'), frames=frames))
    return dict(draft_sha256=digest(directory/'draft.json'), plan_sha256=digest(directory/'plan.json'),
                source_frames_only=True, native_render_verified=False, canvas=data.get('canvas_config'),
                static_overlays=overlays, cards=cards)


def review_bundle(directory, out):
    directory, project, _ = transaction(directory)
    out = Path(out).expanduser().resolve()
    require(not out.exists() and not out.is_relative_to(project), 'Use a fresh review folder outside the project')
    facts = visual_review_facts(directory)
    import shutil
    import tempfile
    from review_labels import footer_ppm
    ffmpeg = shutil.which('ffmpeg')
    require(ffmpeg, 'FFmpeg required to assemble source review sheets')
    out.mkdir(parents=True)
    display_dir = out/'frames'; display_dir.mkdir()
    canvas = facts['canvas'] or dict(width=1920, height=1080)
    display_height = round(960*canvas['height']/canvas['width']/2)*2
    footer_height = 56
    legend = 'YELLOW BOUNDS | CYAN = IMAGE OVERLAY - NOT TEXT'
    pages = []
    for card in facts['cards']:
        bounds = card['bounds']
        overlay = ''
        if bounds:
            l, b, r, t = bounds
            overlay = f'drawbox=x=iw*{(l+1)/2}:y=ih*{(1-t)/2}:w=iw*{(r-l)/2}:h=ih*{(t-b)/2}:color=yellow:t=3,'
        for offset in range(0, len(card['frames']), 9):
            frames = card['frames'][offset:offset+9]
            target = out/f"{card['id']}-{offset//9+1:02d}.jpg"
            chunks, displays = [], []
            for index, frame in enumerate(frames, offset):
                raw = Path(frame['file']).read_bytes()
                require(raw[:3] == b'\xff\xd8\xff', 'Review sheets require the JPEG frames produced by probe')
                geometry = frame.get('review_framing')
                require(not geometry or geometry['status'] in ('static_uniform', 'static_overlay_extent'),
                        'Unsupported review framing: '+str(geometry))
                filters = []
                if geometry:
                    if geometry['status'] == 'static_overlay_extent':
                        l, b, r, t = geometry['bounds']
                        require(l <= -1 and b <= -1 and r >= 1 and t >= 1,
                                'Photo hold exposes canvas background; separate native geometry review is required')
                        l, b, r, t = ((-2-l-r)/(r-l), (-2-b-t)/(t-b), (2-l-r)/(r-l), (2-b-t)/(t-b))
                    else:
                        l, b, r, t = geometry['crop']
                    filters.append(f'crop=w=iw*{(r-l)/2}:h=ih*{(t-b)/2}:x=iw*{max(0., (l+1)/2)}:y=ih*{max(0., (1-t)/2)}:exact=1')
                filters.append(f'scale=960:{display_height}')
                for asset in facts['static_overlays']:
                    if not asset['start'] <= frame['timeline_time'] < asset['end']:
                        continue
                    extent = asset['review_framing']
                    require(extent['status'] == 'static_overlay_extent', 'Unsupported static overlay framing: '+str(extent))
                    l, b, r, t = extent['bounds']
                    filters.append(f'drawbox=x=iw*{(l+1)/2}:y=ih*{(1-t)/2}:w=iw*{(r-l)/2}:h=ih*{(t-b)/2}:color=cyan:t=2')
                if overlay and frame['inside_hold']:
                    filters.append(overlay.rstrip(','))
                status = 'IN CARD' if frame['inside_hold'] else 'CONTEXT-CARD HIDDEN'
                source_time = frame.get('source_time')
                source_label = (f'{source_time:.3f}S' if type(source_time) in (int, float) and
                                math.isfinite(source_time) else 'UNKNOWN')
                label = f"{index:03d} T{frame['timeline_time']:.3f}S SRC{source_label} {status}"
                # Keep all evidence pixels: annotations sit outside the picture.
                display = display_dir/f"{card['id']}-{index:03d}.jpg"
                with tempfile.TemporaryDirectory(prefix='.review-label-', dir=out) as label_dir:
                    footer = Path(label_dir)/'footer.ppm'
                    footer.write_bytes(footer_ppm([label, legend], height=footer_height))
                    rendered = subprocess.run([ffmpeg, '-v', 'error', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-i', '-',
                        '-i', str(footer), '-filter_complex', f"[0:v]{','.join(filters)}[picture];[picture][1:v]vstack=inputs=2[out]",
                        '-map', '[out]', '-frames:v', '1', '-threads', '1',
                        '-q:v', '3', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'], input=raw, capture_output=True)
                require(rendered.returncode == 0 and rendered.stdout[:3] == b'\xff\xd8\xff',
                        'Framed review image failed: '+rendered.stderr.decode(errors='replace')[-700:])
                display.write_bytes(rendered.stdout); chunks.append(rendered.stdout)
                displays.append(dict(source_file=frame['file'], file=str(display), sha256=digest(display), label=label))
            process = subprocess.run([ffmpeg, '-v', 'error', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-i', '-',
                                      '-vf', 'scale=480:-2,tile=3x3:padding=3:margin=3',
                                      '-frames:v', '1', '-q:v', '3', '-y', str(target)],
                                     input=b''.join(chunks), capture_output=True)
            require(process.returncode == 0 and target.is_file(), 'Review sheet failed: '+process.stderr.decode(errors='replace')[-700:])
            pages.append(dict(card_id=card['id'], sheet=str(target), sha256=digest(target), frames=frames, display_frames=displays))
    bundle = dict(version=1, stage=str(directory), facts=facts, pages=pages,
                  display_geometry=dict(picture_width=960, picture_height=display_height, footer_height=footer_height),
                  display_legend=legend,
                  note='Static same-aspect zoom/pan reconstructed from actual draft; yellow=declared card, cyan=static image extent. NOT native text/effects/compositing. Open display_frames for full-size geometry review and frames for raw source evidence. Read frame order/times in JSON. Review both who is visible and which person the label points at.')
    path = out/'bundle.json'; path.write_bytes(encoded(bundle))
    return dict(bundle=str(path), cards=len(facts['cards']), pages=len(pages), native_render_verified=False)


def validate_visual_review(directory, verdict):
    plan = read(directory/'plan.json')
    if plan.get('version') == 1 and verdict is None:
        return
    require(verdict is not None, 'New plans require an independent visual review before apply; generate a review bundle')
    verdict = read(Path(verdict).expanduser().resolve(strict=True))
    require(verdict.get('version') == 1 and verdict.get('independent') is True and verdict.get('reviewer'),
            'Record an independent reviewer; author review is not independent')
    bundle_path = Path(verdict['bundle']).expanduser().resolve(strict=True)
    require(digest(bundle_path) == verdict.get('bundle_sha256'), 'Reviewed visual bundle changed')
    bundle = read(bundle_path)
    facts = visual_review_facts(directory)
    require(bundle.get('stage') == str(directory) and bundle.get('facts') == facts, 'Visual review is stale or covers a different staged product')
    for page in bundle['pages']:
        require(digest(page['sheet']) == page['sha256'], 'Reviewed source sheet changed')
        require([f['source_file'] for f in page.get('display_frames', [])] == [f['file'] for f in page['frames']],
                'Reviewed display frames are incomplete')
        require(all(digest(f['file']) == f['sha256'] for f in page['display_frames']), 'Reviewed display frame changed')
    require({p['card_id'] for p in bundle['pages']} == {c['id'] for c in facts['cards']}, 'Visual bundle pages are incomplete')
    for card in facts['cards']:
        require([f for p in bundle['pages'] if p['card_id'] == card['id'] for f in p['frames']] == card['frames'],
                'Visual bundle pages do not cover every actual frame')
    reviews = verdict.get('cards', [])
    require(len(reviews) == len(facts['cards']) and {r.get('id') for r in reviews} == {c['id'] for c in facts['cards']},
            'Independent review must cover every card')
    for card in facts['cards']:
        review = next(r for r in reviews if r['id'] == card['id'])
        observed = review.get('frames', [])
        require(len(observed) == len(card['frames']) and {r.get('file') for r in observed} == {f['file'] for f in card['frames']},
                'Independent review must observe every bundled frame')
        for frame in card['frames']:
            row = next(r for r in observed if r['file'] == frame['file'])
            require(isinstance(row.get('observation'), str) and row['observation'].strip(), 'Record actual per-frame observations')
            if not frame['inside_hold']:
                continue
            require(row.get('layout_passed') is True, 'Independent visual review rejected card layout: '+card['id'])
            if card['kind'] == 'character':
                require(set(card['characters']) <= set(row.get('subjects', [])) and
                        set(row.get('associated_characters', [])) == set(card['characters']),
                        'Independent review rejected character identity/label association: '+card['id'])
        require(review.get('reading_time_review') and review.get('first_appearance_review' if card['kind']=='character' else 'necessity_review'),
                'Independent review must assess reading time and first entrance/card necessity')
        require(review.get('reading_time_passed') is True, 'Independent review rejected reading time: '+card['id'])
        criterion = 'first_appearance_passed' if card['kind'] == 'character' else 'necessity_passed'
        require(review.get(criterion) is True, 'Independent review rejected first entrance/card necessity: '+card['id'])
    require(verdict.get('native_render_verified') is False,
            'Source-only review cannot establish native rendering; keep native acceptance separate')


def apply(directory, review=None):
    directory, project, meta = transaction(directory)
    validate_visual_review(directory, review)
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
                atomic(project/name, staged_file(directory, name).read_bytes())
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
        build.add_argument('--font', type=Path, help='Explicit installed font override; restyle otherwise preserves saved fonts')
    bundle_parser = sub.add_parser('review', help='Assemble neutral full-hold source/declared-box sheets from a stage')
    bundle_parser.add_argument('stage', type=Path); bundle_parser.add_argument('--out', type=Path, required=True)
    preview_parser = sub.add_parser('preview', help='Reconstruct text/motion preview with explicit observed typography; not native CapCut output')
    preview_parser.add_argument('stage', type=Path)
    preview_parser.add_argument('--calibration', type=Path, required=True)
    preview_parser.add_argument('--out', type=Path, required=True)
    for command in ('apply', 'verify', 'restore'):
        item = sub.add_parser(command); item.add_argument('stage', type=Path)
        if command == 'apply':
            item.add_argument('--review', type=Path, help='Independent per-frame source review verdict for new plans')
    args = parser.parse_args()
    if args.command == 'projects':
        output = [{'name': p.name, 'path': str(p)} for root in project_roots() if root.is_dir() for p in root.iterdir() if (p/'draft_info.json').is_file()]
    elif args.command == 'inspect':
        output = inspect(resolve(args.project))
    elif args.command == 'probe':
        from media import probe
        output = probe(inspect(resolve(args.project)), args.at, args.before, args.after, args.out)
    elif args.command in ('stage', 'restyle'):
        output = {'stage': str(stage(resolve(args.project), read(args.plan), args.out, args.font,
                                    preserve_owned=args.command == 'restyle')), 'applied': False}
    elif args.command == 'review':
        output = review_bundle(args.stage, args.out)
    elif args.command == 'preview':
        from preview import preview
        rendered = preview(args.stage, args.calibration, args.out)
        output = dict(preview=rendered['preview'], manifest=str(args.out.expanduser().resolve()/'manifest.json'),
                      native_render_verified=False, windows=len(rendered['windows']),
                      glyph_overflows=sum(row['overflow'] for row in rendered['text_bounds']),
                      unevaluated_features=len(rendered['unsupported']))
    elif args.command == 'apply':
        output = apply(args.stage, args.review)
    else:
        output = globals()[args.command](args.stage)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
