"""Restrained starting points; choose a local font for the actual film."""
import re

THEMES = {
    'heritage-drama': ('#F1EBDB', '#C5BFB0', 6.7, 3.05, .12, .2, .4),
    'modern-thriller': ('#E8EDF0', '#AEBAC3', 5.8, 2.8, .16, .22, .28),
    'documentary': ('#F5F3ED', '#D2D0C8', 5.5, 2.8, .06, .08, .25),
    'intimate-romance': ('#F4E7DF', '#CCB8AD', 6.2, 2.9, .06, .12, .6),
    'noir': ('#EAE7DE', '#BBB8AF', 6.3, 2.9, .15, .2, .35),
}
FIELDS = ('title_color', 'detail_color', 'title_size', 'detail_size', 'title_spacing', 'detail_spacing', 'fade_seconds')


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
