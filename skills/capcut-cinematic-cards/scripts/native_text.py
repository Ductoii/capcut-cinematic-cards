"""Native editable text shapes for the unencrypted 360000 draft schema."""
import json
import uuid
import copy
from pathlib import Path

from styles import CARD_THEME_PRESETS, SUBTITLE_PRESETS, ensure_capcut_font, hex_to_rgb_floats

FADE_IN_EFFECT_ID = '6724916044072227332'
FADE_OUT_EFFECT_ID = '6724919382104871427'


def identity(project_id, role):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'capcut-cinematic-cards/{project_id}/{role}')).upper()


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def make_native_fade_animation(anim_id, card_duration_us, fade_in_us=700000, fade_out_us=500000):
    """Build native CapCut sticker_animation with Fade In (0.7s) + Fade Out (0.5s)."""
    home = str(Path.home())
    in_dur = min(int(fade_in_us), max(100000, card_duration_us // 3))
    out_dur = min(int(fade_out_us), max(100000, card_duration_us // 3))
    return {
        'id': anim_id,
        'type': 'sticker_animation',
        'multi_language_current': 'none',
        'animations': [
            {
                'anim_adjust_params': None,
                'category_id': 'in',
                'category_name': 'In',
                'duration': in_dur,
                'id': FADE_IN_EFFECT_ID,
                'material_type': 'sticker',
                'name': 'Fade In',
                'panel': '',
                'path': f'{home}/Library/Application Support/CapCut/User Data/Cache/effect/{FADE_IN_EFFECT_ID}/da067c324258f658d9bc9229ffc6dd82',
                'platform': 'all',
                'request_id': '',
                'resource_id': FADE_IN_EFFECT_ID,
                'start': 0,
                'third_resource_id': FADE_IN_EFFECT_ID,
                'type': 'in',
            },
            {
                'anim_adjust_params': None,
                'category_id': 'out',
                'category_name': 'Out',
                'duration': out_dur,
                'id': FADE_OUT_EFFECT_ID,
                'material_type': 'sticker',
                'name': 'Fade Out',
                'panel': '',
                'path': f'{home}/Library/Application Support/CapCut/User Data/Cache/effect/{FADE_OUT_EFFECT_ID}/7280a5ade12bedd6c3ed3fb7eb69fb39',
                'platform': 'all',
                'request_id': '',
                'resource_id': FADE_OUT_EFFECT_ID,
                'start': max(0, card_duration_us - out_dur),
                'third_resource_id': FADE_OUT_EFFECT_ID,
                'type': 'out',
            },
        ],
    }


def make_card_from_preset(project_id, card, detail=False, theme_name='warm-heritage', fade_in_us=700000, fade_out_us=500000):
    """Build a native text material, segment, and native Fade In/Out animation for version 3 plans."""
    preset = CARD_THEME_PRESETS.get(theme_name, CARD_THEME_PRESETS['warm-heritage'])
    is_ending = card.get('kind', card.get('type')) == 'ending'
    raw_text = card.get('detail', '') if detail else card.get('title', card.get('main', ''))
    if detail and preset.get('detail_prefix') and raw_text and not raw_text.startswith('✦'):
        text = preset['detail_prefix'] + raw_text
    else:
        text = raw_text

    role = 'detail' if detail else 'title'
    ident = identity(project_id, card['id'] + ('/detail' if detail else '/title'))
    anim_id = identity(project_id, card['id'] + ('/detail/anim' if detail else '/title/anim'))

    font_ps = card.get(f'{role}_font_ps') or preset[f'{role}_font_ps']
    font_path = Path(card.get(f'{role}_font_path') or ensure_capcut_font(font_ps))
    size = float(card.get(f'{role}_size') or (preset['ending_size'] if (is_ending and not detail) else preset[f'{role}_size']))
    hex_color = card.get(f'{role}_color') or preset[f'{role}_color']
    fill_rgb = hex_to_rgb_floats(hex_color)
    border_hex = card.get('border_color') or preset['border_color']
    border_rgb = hex_to_rgb_floats(border_hex)
    border_width = float(preset['detail_border_width'] if detail else preset['title_border_width'])
    border_alpha = float(preset['border_alpha'])
    spacing = float(preset[f'{role}_spacing'])

    content_obj = {
        'text': text,
        'styles': [
            {
                'fill': {
                    'alpha': 1.0,
                    'content': {'render_type': 'solid', 'solid': {'alpha': 1.0, 'color': fill_rgb}},
                },
                'range': [0, utf16_length(text)],
                'size': size,
                'bold': False,
                'italic': False,
                'underline': False,
                'font': {'id': '', 'path': str(font_path)},
                'letter_spacing': spacing,
                'strokes': [
                    {
                        'alpha': border_alpha,
                        'width': border_width,
                        'content': {'render_type': 'solid', 'solid': {'alpha': border_alpha, 'color': border_rgb}},
                    }
                ],
                'shadows': [
                    {
                        'alpha': float(preset['shadow_alpha']),
                        'angle': float(preset['shadow_angle']),
                        'blur': float(preset['shadow_smoothing']),
                        'color': '#000000',
                        ' content': {},
                        'content': {'render_type': 'solid', 'solid': {'alpha': float(preset['shadow_alpha']), 'color': [0.0, 0.0, 0.0]}},
                        'diffuse': float(preset['shadow_smoothing']),
                        'distance': float(preset['shadow_distance']),
                        'feather': float(preset['shadow_smoothing']),
                        'thickness_projection_angle': -45,
                        'thickness_projection_distance': 0,
                        'thickness_projection_enable': False,
                    }
                ],
            }
        ],
    }
    content_obj['styles'][0]['shadows'][0].pop(' content', None)

    material = dict(
        id=ident,
        type='text',
        name=text,
        base_content=text,
        content=json.dumps(content_obj, ensure_ascii=False, separators=(',', ':')),
        font_path=str(font_path),
        font_name=font_ps,
        font_title=font_ps,
        font_size=size,
        font_id='',
        font_resource_id='',
        font_url=str(font_path),
        fonts=[],
        global_alpha=1.0,
        text_alpha=1.0,
        text_color=hex_color,
        alignment=1,
        typesetting=0,
        text_size=30,
        initial_scale=1.0,
        letter_spacing=spacing,
        line_spacing=0.02,
        line_feed=1,
        use_effect_default_color=False,
        is_rich_text=False,
        has_shadow=True,
        shadow_color='#000000',
        shadow_alpha=float(preset['shadow_alpha']),
        shadow_smoothing=float(preset['shadow_smoothing']),
        shadow_distance=float(preset['shadow_distance']),
        shadow_angle=float(preset['shadow_angle']),
        shadow_point={'x': 1.41421356, 'y': -1.41421356},
        border_color=border_hex,
        border_alpha=border_alpha,
        border_width=border_width,
        bold_width=0.0,
        italic_degree=0,
        underline=False,
        background_color='',
        background_alpha=0.0,
        background_style=0,
        fixed_width=-1.0,
        fixed_height=-1.0,
        force_apply_line_max_width=False,
        line_max_width=0.82,
        text_to_audio_ids=[],
        group_id='',
        recognize_task_id='',
        recognize_text='',
        recognize_model='',
        punc_model='',
        sub_type=0,
        words={'start_time': [], 'end_time': [], 'text': []},
        current_words={'start_time': [], 'end_time': [], 'text': []},
        check_flag=15,
        source_from='',
        multi_language_current='none',
    )

    stagger_us = int(card.get('detail_stagger_us', 180000)) if detail else 0
    start_us = int(card['_start_us']) + stagger_us
    end_us = int(card['_end_us'])
    duration_us = max(300000, end_us - start_us)

    x = float(card.get('x', 0.0 if is_ending else -0.50))
    dy = float(card.get('dy', 0.11))
    y_base = float(card.get('y', 0.02 if is_ending else 0.72))
    y = round(y_base - (dy if detail else 0.0), 4)

    anim_obj = make_native_fade_animation(anim_id, duration_us, fade_in_us=fade_in_us, fade_out_us=fade_out_us)

    segment = dict(
        id=identity(ident, 'segment'),
        material_id=ident,
        source_timerange=None,
        target_timerange={'start': start_us, 'duration': duration_us},
        render_timerange={'start': 0, 'duration': 0},
        desc='',
        state=0,
        speed=1.0,
        is_loop=False,
        is_tone_modify=False,
        reverse=False,
        intensifies_audio=False,
        cartoon=False,
        volume=1.0,
        last_nonzero_volume=1.0,
        visible=True,
        group_id='',
        track_attribute=0,
        clip={
            'scale': {'x': 1.0, 'y': 1.0},
            'rotation': 0.0,
            'transform': {'x': x, 'y': y},
            'flip': {'vertical': False, 'horizontal': False},
            'alpha': 1.0,
        },
        uniform_scale={'on': True, 'value': 1.0},
        extra_material_refs=[anim_id],
        keyframe_refs=[],
        render_index=15000 if detail else 14000,
        track_render_index=0,
        hdr_settings=None,
        hdr_vivid_settings=None,
        common_keyframes=[],
        caption_info=None,
        is_placeholder=False,
        template_id='',
        template_scene='default',
        source='segmentsourcenormal',
        responsive_layout={'enable': False, 'target_follow': '', 'size_layout': 0, 'horizontal_pos_layout': 0, 'vertical_pos_layout': 0},
    )
    for option in ('lut', 'adjust', 'hsl', 'color_curves', 'hsl_curves', 'color_wheels', 'smart_color_adjust',
                   'color_match_adjust', 'color_correct_adjust', 'adjust_mask', 'video_mask', 'mask_stroke', 'mask_shadow', 'color_adjust_pro'):
        segment['enable_' + option] = False
    apply_text_layout(material, segment, card, detail)
    return material, segment, anim_obj


def balance_subtitle_lines(text, wrap_width=42):
    """Wrap single-line text into at most two balanced lines without altering words."""
    words = text.split()
    flat = ' '.join(words)
    if not wrap_width or len(flat) <= wrap_width or len(words) < 2:
        return flat
    best = None
    best_score = 10**9
    for idx in range(1, len(words)):
        line1 = ' '.join(words[:idx])
        line2 = ' '.join(words[idx:])
        score = max(len(line1), len(line2)) * 3 + abs(len(line1) - len(line2))
        if max(len(line1), len(line2)) <= wrap_width:
            score -= 500
        if score < best_score:
            best_score = score
            best = f'{line1}\n{line2}'
    return best or flat


def apply_subtitle_preset_in_place(data, preset_name='white-cinematic-boxless', y=None, wrap_width=None,
                                   text_overrides=None, remove_segment_ids=None):
    """Style native CapCut Auto-Captions in-place with zero timing drift."""
    if preset_name not in SUBTITLE_PRESETS:
        raise ValueError(f'Unknown subtitle preset: {preset_name}')
    preset = SUBTITLE_PRESETS[preset_name]
    font_path = ensure_capcut_font(preset['font_ps'])
    target_y = float(y if y is not None else preset['y'])
    target_wrap = int(wrap_width if wrap_width is not None else preset['wrap_width'])
    text_overrides = text_overrides or {}
    remove_ids = set(remove_segment_ids or [])

    result = copy.deepcopy(data)
    materials = {m['id']: m for m in result['materials'].get('texts', [])}
    removed_materials = set()
    removed_tasks = set()
    styled_count = 0

    fill_rgb = hex_to_rgb_floats(preset['text_color'])
    border_rgb = hex_to_rgb_floats(preset['border_color'])

    for track in result['tracks']:
        if track.get('type') != 'text':
            continue
        kept_segments = []
        for segment in track.get('segments', []):
            mat_id = segment.get('material_id')
            mat = materials.get(mat_id, {})
            if mat.get('type') != 'subtitle':
                kept_segments.append(segment)
                continue
            if segment['id'] in remove_ids or mat_id in remove_ids:
                removed_materials.add(mat_id)
                if mat.get('recognize_task_id'):
                    removed_tasks.add(mat['recognize_task_id'])
                continue

            content = json.loads(mat['content'])
            if segment['id'] in text_overrides:
                new_text = text_overrides[segment['id']]
            elif mat_id in text_overrides:
                new_text = text_overrides[mat_id]
            else:
                new_text = balance_subtitle_lines(content.get('text', ''), wrap_width=target_wrap)

            style_obj = {
                'fill': {
                    'alpha': 1.0,
                    'content': {'render_type': 'solid', 'solid': {'alpha': 1.0, 'color': fill_rgb}},
                },
                'font': {'id': '', 'path': str(font_path)},
                'range': [0, utf16_length(new_text)],
                'size': float(preset['font_size']),
                'bold': False,
                'italic': False,
                'underline': False,
                'letter_spacing': float(preset['letter_spacing']),
                'strokes': [
                    {
                        'alpha': float(preset['border_alpha']),
                        'width': float(preset['border_width']),
                        'content': {
                            'render_type': 'solid',
                            'solid': {'alpha': float(preset['border_alpha']), 'color': border_rgb},
                        },
                    }
                ],
                'shadows': (
                    [
                        {
                            'alpha': float(preset['shadow_alpha']),
                            'angle': float(preset['shadow_angle']),
                            'blur': float(preset['shadow_smoothing']),
                            'color': preset['shadow_color'],
                            'content': {
                                'render_type': 'solid',
                                'solid': {'alpha': float(preset['shadow_alpha']), 'color': [0.0, 0.0, 0.0]},
                            },
                            'diffuse': float(preset['shadow_smoothing']),
                            'distance': float(preset['shadow_distance']),
                            'feather': float(preset['shadow_smoothing']),
                            'thickness_projection_angle': -45,
                            'thickness_projection_distance': 0,
                            'thickness_projection_enable': False,
                        }
                    ]
                    if preset['has_shadow']
                    else []
                ),
            }

            content['text'] = new_text
            content['styles'] = [style_obj]
            mat['content'] = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
            mat['base_content'] = new_text
            mat['name'] = new_text.replace('\n', ' ')
            mat['font_path'] = str(font_path)
            mat['font_url'] = str(font_path)
            mat['font_name'] = preset['font_ps']
            mat['font_title'] = preset['font_ps']
            mat['font_id'] = ''
            mat['font_resource_id'] = ''
            mat['fonts'] = []
            mat['font_size'] = float(preset['font_size'])
            mat['text_color'] = preset['text_color']
            mat['text_alpha'] = 1.0
            mat['global_alpha'] = 1.0
            mat['alignment'] = 1
            mat['typesetting'] = 0
            mat['letter_spacing'] = float(preset['letter_spacing'])
            mat['line_spacing'] = float(preset['line_spacing'])
            mat['line_max_width'] = 0.86
            mat['force_apply_line_max_width'] = False
            mat['fixed_width'] = -1.0
            mat['fixed_height'] = -1.0
            mat['check_flag'] = int(preset['check_flag'])
            mat['border_color'] = preset['border_color']
            mat['border_width'] = float(preset['border_width'])
            mat['border_alpha'] = float(preset['border_alpha'])
            mat['has_shadow'] = bool(preset['has_shadow'])
            mat['shadow_color'] = preset['shadow_color']
            mat['shadow_alpha'] = float(preset['shadow_alpha'])
            mat['shadow_smoothing'] = float(preset['shadow_smoothing'])
            mat['shadow_distance'] = float(preset['shadow_distance'])
            mat['shadow_angle'] = float(preset['shadow_angle'])
            mat['background_style'] = int(preset['background_style'])
            mat['background_alpha'] = float(preset['background_alpha'])
            mat['background_color'] = preset['background_color']
            if preset['background_style'] > 0:
                mat['background_round_radius'] = float(preset.get('background_round_radius', 0.22))
                mat['background_height'] = float(preset.get('background_height', 0.14))
                mat['background_width'] = float(preset.get('background_width', 0.14))
                mat['background_horizontal_offset'] = 0.0
                mat['background_vertical_offset'] = 0.0
            else:
                mat['background_round_radius'] = 0.0
                mat['text_bg_alpha'] = 0.0
                mat['text_bg_round_radius_ratio'] = 0.0

            segment.setdefault('clip', {})
            segment['clip']['transform'] = {'x': 0.0, 'y': target_y}
            segment['clip']['scale'] = {'x': 1.0, 'y': 1.0}
            segment['uniform_scale'] = {'on': True, 'value': 1.0}
            kept_segments.append(segment)
            styled_count += 1
        track['segments'] = kept_segments

    if removed_materials:
        result['materials']['texts'] = [m for m in result['materials'].get('texts', []) if m.get('id') not in removed_materials]

    return result, {
        'preset': preset_name,
        'font_path': str(font_path),
        'styled_segments': styled_count,
        'removed_materials': sorted(removed_materials),
        'removed_recognize_tasks': sorted(removed_tasks),
    }


def make_text(project_id, card, detail, font, fps):
    text = card.get('detail', '') if detail else card['title']
    ident = identity(project_id, card['id'] + ('/detail' if detail else '/title'))
    style = card['_style']
    role = 'detail' if detail else 'title'
    size = style[role + '_size']
    hex_color = style[role + '_color']
    colour = [int(hex_color[i:i+2], 16)/255 for i in (1, 3, 5)]
    shadow = {'thickness_projection_distance': 0, 'thickness_projection_angle': -45,
              'feather': .08, 'distance': 2., 'content': {'solid': {'color': [0, 0, 0]}, 'render_type': 'solid'},
              'thickness_projection_enable': False, 'angle': -45}
    content = {'text': text, 'styles': [{'fill': {'content': {'solid': {'color': colour}}, 'render_type': 'solid'},
                'range': [0, utf16_length(text)], 'size': size, 'font': {'path': str(font), 'id': ''},
                'letter_spacing': style[role + '_spacing'], 'shadows': [shadow]}]}
    material = dict(id=ident, type='text', name=text, content=json.dumps(content, ensure_ascii=False, separators=(',', ':')),
                    font_path=str(font), font_name=font.stem, font_title=font.stem, font_size=size, font_id='', font_resource_id='',
                    font_url='', fonts=[], global_alpha=1., text_alpha=1., text_color=hex_color,
                    alignment=1, typesetting=0, text_size=30, initial_scale=1., letter_spacing=style[role + '_spacing'],
                    line_spacing=.02, line_feed=1, use_effect_default_color=False, is_rich_text=False,
                    has_shadow=True, shadow_color='#000000', shadow_alpha=.75, shadow_smoothing=.08,
                    shadow_distance=2., shadow_angle=-45., shadow_point={'x': 1.41421356, 'y': -1.41421356},
                    border_alpha=0., border_width=0., bold_width=0., italic_degree=0, underline=False,
                    background_color='', background_alpha=0., background_style=0, fixed_width=-1., fixed_height=-1.,
                    force_apply_line_max_width=False, line_max_width=.82, text_to_audio_ids=[], group_id='',
                    recognize_task_id='', recognize_text='', recognize_model='', punc_model='', sub_type=0,
                    words={'start_time': [], 'end_time': [], 'text': []}, current_words={'start_time': [], 'end_time': [], 'text': []},
                    check_flag=15, source_from='', multi_language_current='none')
    duration = card['_end_us'] - card['_start_us']
    frames = max(1, round(duration * fps / 1e6))
    fade = max(1, min(round(style['fade_seconds'] * fps), (frames-1)//3))
    points = [(0, 0), (fade//3, .18), (2*fade//3, .82), (fade, 1),
              (frames-1-fade, 1), (frames-1-2*fade//3, .82), (frames-1-fade//3, .18), (frames-1, 0)]
    keys = [dict(id=identity(ident, f'alpha/{frame}'), curveType='Line', time_offset=round(frame*1e6/fps),
                 left_control={'x': 0., 'y': 0.}, right_control={'x': 0., 'y': 0.}, values=[value], string_value='', graphID='')
            for frame, value in points]
    layout = card.get('layout', 'lower-left')
    x = card.get('x', -.52 if layout == 'lower-left' else 0.)
    y = card.get('y', -.66 if layout == 'lower-left' else .035) - (.13 if detail else 0.)
    segment = dict(id=identity(ident, 'segment'), material_id=ident, source_timerange=None,
                   target_timerange={'start': card['_start_us'], 'duration': duration}, render_timerange={'start': 0, 'duration': 0},
                   desc='', state=0, speed=1., is_loop=False, is_tone_modify=False, reverse=False, intensifies_audio=False,
                   cartoon=False, volume=1., last_nonzero_volume=1., visible=True, group_id='', track_attribute=0,
                   clip={'scale': {'x': 1., 'y': 1.}, 'rotation': 0., 'transform': {'x': x, 'y': y},
                         'flip': {'vertical': False, 'horizontal': False}, 'alpha': 1.},
                   uniform_scale={'on': True, 'value': 1.}, extra_material_refs=[], keyframe_refs=[],
                   render_index=15000 if detail else 14000, track_render_index=0, hdr_settings=None, hdr_vivid_settings=None,
                   common_keyframes=[{'id': identity(ident, 'alpha'), 'material_id': '', 'property_type': 'KFTypeAlpha', 'keyframe_list': keys}],
                   caption_info=None, is_placeholder=False, template_id='', template_scene='default', source='segmentsourcenormal',
                   responsive_layout={'enable': False, 'target_follow': '', 'size_layout': 0, 'horizontal_pos_layout': 0, 'vertical_pos_layout': 0})
    for option in ('lut', 'adjust', 'hsl', 'color_curves', 'hsl_curves', 'color_wheels', 'smart_color_adjust',
                   'color_match_adjust', 'color_correct_adjust', 'adjust_mask', 'video_mask', 'mask_stroke', 'mask_shadow', 'color_adjust_pro'):
        segment['enable_' + option] = False
    approved = card.get('_appearance', {}).get(role)
    if approved:
        material.update(copy.deepcopy(approved['appearance']))
        rich_style = copy.deepcopy(approved['rich_content_example']['styles'][0])
        rich_style['range'] = [0, utf16_length(text)]
        material['content'] = json.dumps({'text': text, 'styles': [rich_style]},
                                         ensure_ascii=False, separators=(',', ':'))
        material['base_content'] = material['content']
        segment['clip']['scale'] = copy.deepcopy(approved['clip_scale'])
        segment['uniform_scale'] = copy.deepcopy(approved['uniform_scale'])
    apply_text_layout(material, segment, card, detail)
    return material, segment


def apply_text_layout(material, segment, card, detail=False):
    """Only explicit layout overrides; never infer px from native text units."""
    options = card.get('text_layout', {})
    role = 'detail' if detail else 'title'
    for axis in ('x', 'y'):
        if role+'_'+axis in options:
            segment['clip']['transform'][axis] = options[role+'_'+axis]
    if 'scale' in options:
        scale = options['scale']
        segment['clip']['scale'] = {'x': scale, 'y': scale}
        segment['uniform_scale'] = {'on': True, 'value': scale}
    if 'line_max_width' in options:
        material['line_max_width'] = options['line_max_width']
        material['force_apply_line_max_width'] = True
    if 'fixed_width' in options:
        material['fixed_width'] = options['fixed_width']


def restyle_subtitles(data, template, y=None, wrap_columns=None, cue_positions=None):
    """Copy a reviewed native appearance, retaining recognition data and cue timing."""
    source_content = json.loads(template['content'])
    if len(source_content.get('styles', [])) != 1:
        raise ValueError('Subtitle template must have one reviewed native style')
    fields = {'alignment', 'typesetting', 'text_size', 'initial_scale', 'letter_spacing', 'line_spacing',
              'line_feed', 'use_effect_default_color', 'is_rich_text', 'has_shadow', 'underline',
              'fixed_width', 'fixed_height', 'force_apply_line_max_width', 'line_max_width',
              'text_alpha', 'global_alpha', 'text_color', 'inner_padding', 'check_flag', 'fonts'}
    fields.update(k for k in template if k.startswith(('font_', 'background_', 'shadow_', 'border_', 'bold_', 'italic_')))
    result = copy.deepcopy(data)
    materials = {m['id']: m for m in result['materials'].get('texts', [])}
    changes = []
    cue_positions = cue_positions or {}
    remaining = set(cue_positions)
    material_wraps = {}
    for track in result['tracks']:
        if track.get('type') != 'text':
            continue
        for segment in track.get('segments', []):
            ident = segment.get('material_id')
            if materials.get(ident, {}).get('type') == 'subtitle':
                columns = cue_positions.get(segment['id'], {}).get('wrap_columns', wrap_columns)
                widths = material_wraps.setdefault(ident, set())
                widths.add(columns)
                if len(widths) > 1:
                    raise ValueError('Shared subtitle material has conflicting wrap widths: '+ident+
                                     '; review all linked cues with one wrap width')
    for track in result['tracks']:
        if track.get('type') != 'text':
            continue
        for segment in track.get('segments', []):
            material = materials.get(segment.get('material_id'), {})
            if material.get('type') != 'subtitle':
                continue
            content = json.loads(material['content'])
            old_text = content['text']
            text = old_text
            columns = cue_positions.get(segment['id'], {}).get('wrap_columns', wrap_columns)
            if columns:
                words = old_text.split(); flat = ' '.join(words)
                if len(flat) <= columns:
                    text = flat
                else:
                    options = [(' '.join(words[:i]), ' '.join(words[i:])) for i in range(1, len(words))]
                    options = [pair for pair in options if max(map(len, pair)) <= columns]
                    if not options:
                        raise ValueError('Subtitle does not fit two lines at the requested wrap width; review the cue instead of truncating it')
                    text = '\n'.join(min(options, key=lambda pair: abs(len(pair[0])-len(pair[1]))))
            if text.split() != old_text.split():
                raise ValueError('Subtitle wording changed')
            for key in fields:
                if key in template:
                    material[key] = copy.deepcopy(template[key])
            style = copy.deepcopy(source_content['styles'][0])
            style['range'] = [0, len(text)]
            content.update(text=text, styles=[style])
            material['content'] = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
            material['base_content'] = material['content']
            if y is not None:
                segment['clip']['transform']['y'] = y
            if segment['id'] in cue_positions:
                if segment['id'] not in remaining:
                    raise ValueError('Ambiguous native subtitle cue position: '+segment['id'])
                position = cue_positions[segment['id']]
                for axis in ('x', 'y'):
                    if axis in position:
                        segment['clip']['transform'][axis] = position[axis]
                remaining.discard(segment['id'])
            changes.append({'material_id': material['id'], 'segment_id': segment['id'],
                            'before_text': old_text, 'after_text': text,
                            'target_timerange': copy.deepcopy(segment['target_timerange'])})
    if not changes:
        raise ValueError('No native subtitle cues in this project')
    if remaining:
        raise ValueError('Unknown native subtitle cue position: '+', '.join(sorted(remaining)))
    return result, changes
