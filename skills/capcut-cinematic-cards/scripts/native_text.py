"""Native editable text shapes for the unencrypted 360000 draft schema."""
import json
import uuid
import copy


def identity(project_id, role):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'capcut-cinematic-cards/{project_id}/{role}')).upper()


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


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
