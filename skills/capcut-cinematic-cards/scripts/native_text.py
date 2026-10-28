"""Native editable text shapes for the unencrypted 360000 draft schema."""
import json
import uuid


def identity(project_id, role):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'capcut-cinematic-cards/{project_id}/{role}')).upper()


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
                'range': [0, len(text)], 'size': size, 'font': {'path': str(font), 'id': ''}, 'shadows': [shadow]}]}
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
