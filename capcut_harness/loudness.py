"""FFmpeg EBU R128 measurements; non-finite silence is represented by null."""
import json
import math

from .process import run


def measure(path,start=None,end=None,cancelled=lambda:False):
    args=['ffmpeg','-hide_banner','-nostats']
    if start is not None:args+=['-ss',f'{start:.9f}']
    args+=['-i',str(path)]
    if end is not None:args+=['-t',f'{max(.001,end-(start or 0)):.9f}']
    args+=['-vn','-af','apad=pad_dur=0.4,loudnorm=I=-18:TP=-1.5:print_format=json','-f','null','-']
    _,log=run(args,cancelled=cancelled)
    try:
        report=json.JSONDecoder().raw_decode(log[log.rfind('{'):])[0]
        def finite(key):
            value=float(report[key]);return round(value,3) if math.isfinite(value) else None
        return dict(lufs=finite('input_i'),true_peak_dbtp=finite('input_tp'))
    except (ValueError,KeyError) as exc:raise ValueError('FFmpeg returned no loudness measurement') from exc
