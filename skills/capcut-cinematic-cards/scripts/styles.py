"""Film-matched card themes, subtitle presets, and macOS CapCut sandbox font extraction."""
from pathlib import Path
import re

THEMES = {
    'heritage-drama': ('#F1EBDB', '#C5BFB0', 6.7, 3.05, .12, .2, .4),
    'modern-thriller': ('#E8EDF0', '#AEBAC3', 5.8, 2.8, .16, .22, .28),
    'documentary': ('#F5F3ED', '#D2D0C8', 5.5, 2.8, .06, .08, .25),
    'intimate-romance': ('#F4E7DF', '#CCB8AD', 6.2, 2.9, .06, .12, .6),
    'noir': ('#EAE7DE', '#BBB8AF', 6.3, 2.9, .15, .2, .35),
    'warm-heritage': ('#F6EFE2', '#E5B869', 6.2, 3.8, .05, .04, .7),
    'southern-copper': ('#FAF3E6', '#E0A958', 6.2, 3.8, .05, .04, .7),
    'christmas-hearth': ('#FCE8B2', '#F4F7EE', 6.2, 3.8, .05, .04, .7),
}
FIELDS = ('title_color', 'detail_color', 'title_size', 'detail_size', 'title_spacing', 'detail_spacing', 'fade_seconds')

# Mapping of PostScript font names to macOS system .ttc collections for standalone .ttf extraction
FONT_COLLECTION_MAP = {
    'Menlo-Regular': ('/System/Library/Fonts/Menlo.ttc', 0),
    'Menlo-Bold': ('/System/Library/Fonts/Menlo.ttc', 2),
    'Seravek-Regular': ('/System/Library/Fonts/Supplemental/Seravek.ttc', 0),
    'Seravek-Medium': ('/System/Library/Fonts/Supplemental/Seravek.ttc', 4),
    'Seravek-Bold': ('/System/Library/Fonts/Supplemental/Seravek.ttc', 2),
    'Baskerville-SemiBold': ('/System/Library/Fonts/Supplemental/Baskerville.ttc', 4),
    'Baskerville-Bold': ('/System/Library/Fonts/Supplemental/Baskerville.ttc', 2),
    'Optima-Regular': ('/System/Library/Fonts/Optima.ttc', 0),
    'Optima-Bold': ('/System/Library/Fonts/Optima.ttc', 2),
    'Didot-Bold': ('/System/Library/Fonts/Supplemental/Didot.ttc', 2),
    'AvenirNext-Medium': ('/System/Library/Fonts/Avenir Next.ttc', 5),
    'AvenirNext-DemiBold': ('/System/Library/Fonts/Avenir Next.ttc', 2),
    'AvenirNext-Bold': ('/System/Library/Fonts/Avenir Next.ttc', 0),
}

CARD_THEME_PRESETS = {
    'warm-heritage': {
        'title_font_ps': 'Didot-Bold',
        'detail_font_ps': 'AvenirNext-DemiBold',
        'title_color': '#F6EFE2',
        'detail_color': '#E5B869',
        'title_size': 6.2,
        'detail_size': 3.8,
        'ending_size': 7.5,
        'title_spacing': 0.05,
        'detail_spacing': 0.04,
        'border_color': '#100B08',
        'title_border_width': 0.018,
        'detail_border_width': 0.016,
        'border_alpha': 0.92,
        'shadow_alpha': 0.88,
        'shadow_smoothing': 0.28,
        'shadow_distance': 4.5,
        'shadow_angle': -70.0,
        'fade_in_us': 700000,
        'fade_out_us': 500000,
    },
    'southern-copper': {
        'title_font_ps': 'Baskerville-SemiBold',
        'detail_font_ps': 'AvenirNext-Medium',
        'title_color': '#FAF3E6',
        'detail_color': '#E0A958',
        'title_size': 6.2,
        'detail_size': 3.8,
        'ending_size': 7.5,
        'title_spacing': 0.05,
        'detail_spacing': 0.04,
        'border_color': '#120C07',
        'title_border_width': 0.018,
        'detail_border_width': 0.016,
        'border_alpha': 0.92,
        'shadow_alpha': 0.88,
        'shadow_smoothing': 0.28,
        'shadow_distance': 4.5,
        'shadow_angle': -70.0,
        'fade_in_us': 700000,
        'fade_out_us': 500000,
    },
    'christmas-hearth': {
        'title_font_ps': 'Baskerville-Bold',
        'detail_font_ps': 'Optima-Bold',
        'title_color': '#FCE8B2',
        'detail_color': '#F4F7EE',
        'detail_prefix': '✦  ',
        'title_size': 6.2,
        'detail_size': 3.8,
        'ending_size': 7.5,
        'title_spacing': 0.05,
        'detail_spacing': 0.04,
        'border_color': '#1A0D08',
        'title_border_width': 0.018,
        'detail_border_width': 0.016,
        'border_alpha': 0.92,
        'shadow_alpha': 0.88,
        'shadow_smoothing': 0.28,
        'shadow_distance': 4.5,
        'shadow_angle': -70.0,
        'fade_in_us': 700000,
        'fade_out_us': 500000,
    },
    'modern-thriller': {
        'title_font_ps': 'AvenirNext-Bold',
        'detail_font_ps': 'Menlo-Bold',
        'title_color': '#F2F5F8',
        'detail_color': '#D9A441',
        'title_size': 5.8,
        'detail_size': 3.5,
        'ending_size': 7.2,
        'title_spacing': 0.08,
        'detail_spacing': 0.06,
        'border_color': '#080B10',
        'title_border_width': 0.018,
        'detail_border_width': 0.016,
        'border_alpha': 0.92,
        'shadow_alpha': 0.88,
        'shadow_smoothing': 0.26,
        'shadow_distance': 4.0,
        'shadow_angle': -70.0,
        'fade_in_us': 700000,
        'fade_out_us': 500000,
    },
}

SUBTITLE_PRESETS = {
    'white-cinematic-boxless': {
        'font_ps': 'Menlo-Regular',
        'font_size': 4.2,
        'text_color': '#FFFDF8',
        'y': -0.74,
        'wrap_width': 42,
        'check_flag': 15,
        'letter_spacing': 0.01,
        'line_spacing': 0.02,
        'border_color': '#080605',
        'border_width': 0.016,
        'border_alpha': 0.95,
        'has_shadow': True,
        'shadow_color': '#000000',
        'shadow_alpha': 0.88,
        'shadow_smoothing': 0.28,
        'shadow_distance': 4.0,
        'shadow_angle': -70.0,
        'background_style': 0,
        'background_alpha': 0.0,
        'background_color': '',
    },
    'yellow-cinema-boxless': {
        'font_ps': 'Seravek-Medium',
        'font_size': 4.4,
        'text_color': '#E5CE6E',
        'y': -0.78,
        'wrap_width': 44,
        'check_flag': 15,
        'letter_spacing': 0.0,
        'line_spacing': 0.02,
        'border_color': '#080808',
        'border_width': 0.012,
        'border_alpha': 0.92,
        'has_shadow': True,
        'shadow_color': '#000000',
        'shadow_alpha': 0.85,
        'shadow_smoothing': 0.22,
        'shadow_distance': 3.5,
        'shadow_angle': -70.0,
        'background_style': 0,
        'background_alpha': 0.0,
        'background_color': '',
    },
    'boxed-monospaced': {
        'font_ps': 'Menlo-Regular',
        'font_size': 4.1,
        'text_color': '#FFFDF8',
        'y': -0.74,
        'wrap_width': 42,
        'check_flag': 23,
        'letter_spacing': 0.01,
        'line_spacing': 0.02,
        'border_color': '#080605',
        'border_width': 0.008,
        'border_alpha': 0.85,
        'has_shadow': False,
        'shadow_color': '#000000',
        'shadow_alpha': 0.0,
        'shadow_smoothing': 0.0,
        'shadow_distance': 0.0,
        'shadow_angle': -70.0,
        'background_style': 1,
        'background_color': '#14110E',
        'background_alpha': 0.62,
        'background_round_radius': 0.22,
        'background_height': 0.14,
        'background_width': 0.14,
        'background_horizontal_offset': 0.0,
        'background_vertical_offset': 0.0,
    },
}


def hex_to_rgb_floats(hex_color):
    return [round(int(hex_color[i:i + 2], 16) / 255.0, 6) for i in (1, 3, 5)]


def ensure_capcut_font(postscript_name):
    """Extract a standalone .ttf from macOS .ttc into both ~/Library/Fonts and CapCut sandbox."""
    home = Path.home()
    user_fonts = home / 'Library/Fonts'
    sandbox_fonts = home / 'Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts'
    filename = f'{postscript_name}.ttf'
    user_target = user_fonts / filename
    sandbox_target = sandbox_fonts / filename

    if user_target.is_file() and (not sandbox_fonts.parent.exists() or sandbox_target.is_file()):
        return sandbox_target if sandbox_target.is_file() else user_target

    if postscript_name in FONT_COLLECTION_MAP:
        ttc_path_str, default_idx = FONT_COLLECTION_MAP[postscript_name]
        ttc_path = Path(ttc_path_str)
        if ttc_path.is_file():
            try:
                from fontTools.ttLib import TTCollection
                ttc = TTCollection(str(ttc_path))
                chosen = None
                for font in ttc.fonts:
                    for rec in font['name'].names:
                        if rec.nameID == 6 and rec.toUnicode().strip() == postscript_name:
                            chosen = font
                            break
                    if chosen is not None:
                        break
                if chosen is None and 0 <= default_idx < len(ttc.fonts):
                    chosen = ttc.fonts[default_idx]
                if chosen is not None:
                    user_fonts.mkdir(parents=True, exist_ok=True)
                    chosen.save(str(user_target))
                    if sandbox_fonts.parent.exists():
                        sandbox_fonts.mkdir(parents=True, exist_ok=True)
                        chosen.save(str(sandbox_target))
                    return sandbox_target if sandbox_target.is_file() else user_target
            except Exception:
                pass

    # Fallback if already present in system or user fonts
    for candidate in (sandbox_target, user_target, Path('/System/Library/Fonts/Supplemental/Baskerville.ttc')):
        if candidate.is_file():
            return candidate
    return user_target


def measure_card_overflow(text, font_path, font_size, x_norm, canvas_width=1920, margin_px=65):
    """Check pixel bounds of centered card text against [margin_px, canvas_width - margin_px]."""
    px_size = max(12, round(float(font_size) * 13.0))
    width_px = 0
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(str(font_path), px_size)
        for line in str(text).split('\n'):
            bbox = font.getbbox(line)
            w = (bbox[2] - bbox[0]) if bbox else 0
            if w > width_px:
                width_px = w
    except Exception:
        longest = max((len(line) for line in str(text).split('\n')), default=0)
        width_px = round(longest * px_size * 0.58)

    center_x = (float(x_norm) + 1.0) * 0.5 * canvas_width
    left_px = center_x - width_px / 2.0
    right_px = center_x + width_px / 2.0
    clamped_x = float(x_norm)
    if left_px < margin_px:
        new_center = margin_px + width_px / 2.0
        clamped_x = round((new_center / canvas_width) * 2.0 - 1.0, 4)
    elif right_px > (canvas_width - margin_px):
        new_center = (canvas_width - margin_px) - width_px / 2.0
        clamped_x = round((new_center / canvas_width) * 2.0 - 1.0, 4)
    return {
        'width_px': round(width_px, 1),
        'left_px': round(left_px, 1),
        'right_px': round(right_px, 1),
        'overflow': left_px < margin_px or right_px > (canvas_width - margin_px),
        'clamped_x': clamped_x,
    }


def resolve_style(value):
    if not isinstance(value, dict) or set(value) - set(FIELDS) - {'theme'}:
        raise ValueError('Unsupported style field; use documented native typography and opacity options')
    theme = value.get('theme', 'heritage-drama')
    if theme not in THEMES:
        raise ValueError('Unknown style theme')
    result = dict(zip(FIELDS, THEMES[theme]))
    result.update({key: val for key, val in value.items() if key in FIELDS})
    for key in FIELDS[:2]:
        if not isinstance(result[key], str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', result[key]):
            raise ValueError('Style colors must be #RRGGBB')
    for key, low, high in [('title_size', 3, 8), ('detail_size', 1.8, 4.5), ('title_spacing', 0, .3), ('detail_spacing', 0, .3), ('fade_seconds', .2, .8)]:
        val = result[key]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not low <= val <= high:
            raise ValueError(f'Style {key} outside supported range {low}..{high}')
    return result
