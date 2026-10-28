"""Speech-region leveling with a measured, peak-limited PCM master."""
import json
import math
from pathlib import Path

import numpy as np

from .legacy import cards
from .process import run,check_cancel
from .mix import RATE,BLOCK
from .loudness import measure
from .speech import detect

DEFAULTS=dict(target_lufs=-18.,max_boost_db=12.,peak_dbtp=-1.5)


def parameters(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('Unknown audio parameter')
    result={**DEFAULTS,**value}
    for name,(low,high) in dict(target_lufs=(-24,-12),max_boost_db=(0,24),peak_dbtp=(-6,-.5)).items():
        v=result[name]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high:
            raise ValueError(f'Invalid {name}: expected {low}..{high}')
        result[name]=float(v)
    return result


def write_json(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def analyze(mix_path,out,params,progress=lambda *a:None,cancelled=lambda:False):
    parameters(params);check_cancel(cancelled)
    mix_path=Path(mix_path).resolve(strict=True);signature=cards.digest(mix_path)
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    raw=out/'audio.f32'
    with raw.open('wb') as f:
        run(['ffmpeg','-v','error','-i',mix_path,'-vn','-ar',str(RATE),'-ac','2','-f','f32le','-'],stdout=f,cancelled=cancelled)
    samples=raw.stat().st_size//8
    intervals=detect(mix_path,out,cancelled,progress)
    for i,interval in enumerate(intervals):
        check_cancel(cancelled);interval.update(before_lufs=measure(mix_path,interval['start'],interval['end'],cancelled)['lufs'])
        progress('measure-before',i+1,len(intervals))
    if cards.digest(mix_path)!=signature:raise ValueError('Mix changed during analysis')
    report=dict(version=1,mix_path=str(mix_path),mix_sha256=signature,raw_path=str(raw),raw_sha256=cards.digest(raw),
                samples=samples,sample_rate=RATE,channels=2,duration=samples/RATE,intervals=intervals,
                speech_seconds=round(sum(i['end']-i['start'] for i in intervals),3),
                detector='Silero v6 local VAD; candidates, not speaker identification',editor_render_verified=False)
    write_json(out/'analysis.json',report);return report


def statistics(rows,key):
    values=[r[key] for r in rows if not r.get('excluded') and r.get(key) is not None]
    if not values:return dict(median_lufs=None,spread_lu=None,p10_lufs=None,p90_lufs=None)
    p10,p90=np.percentile(values,[10,90]);return dict(median_lufs=round(float(np.median(values)),2),
        spread_lu=round(float(p90-p10),2),p10_lufs=round(float(p10),2),p90_lufs=round(float(p90),2))


def envelope(rows,duration):
    knots=[(0.,0.)]
    for row in rows:
        start,end,gain=row['start'],row['end'],row['gain_db']
        if start-knots[-1][0]>.8:
            if knots[-1][0]>0:knots.append((min(start-.2,knots[-1][0]+.2),0.))
            knots.append((max(knots[-1][0],start-.2),0.))
        knots.extend([(start,gain),(end,gain)])
    if duration>knots[-1][0]:knots.extend([(min(duration,knots[-1][0]+.2),0.),(duration,0.)])
    # Identical-time boundary knots use the later value; interpolation remains deterministic.
    unique={round(t,9):v for t,v in knots};return np.array(sorted(unique)),np.array([unique[t] for t in sorted(unique)])


def render(analysis,out,params,excluded,progress=lambda *a:None,cancelled=lambda:False):
    params=parameters(params);check_cancel(cancelled)
    ids={r['id'] for r in analysis['intervals']}
    if not isinstance(excluded,list) or any(not isinstance(i,str) or i not in ids for i in excluded):raise ValueError('Unknown speech interval exclusion')
    for name,key in [('mix_path','mix_sha256'),('raw_path','raw_sha256')]:
        if cards.digest(analysis[name])!=analysis[key]:raise ValueError('Analyzed mix changed; analyze again')
    rows=[]
    for row in analysis['intervals']:
        r=dict(row,excluded=row['id'] in excluded);level=row.get('before_lufs')
        r['gain_db']=round(float(np.clip(params['target_lufs']-level,-params['max_boost_db'],params['max_boost_db'])),3) if level is not None and not r['excluded'] else 0.
        rows.append(r)
    if not any(not r['excluded'] and r.get('before_lufs') is not None for r in rows):raise ValueError('No accepted speech to normalize')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    raw=out/'leveled.f32';count=analysis['samples'];source=np.memmap(analysis['raw_path'],dtype='<f4',mode='r',shape=(count,2))
    times,gains=envelope(rows,analysis['duration'])
    with raw.open('wb') as f:
        for pos in range(0,count,BLOCK):
            check_cancel(cancelled);end=min(count,pos+BLOCK)
            timeline=np.arange(pos,end,dtype=np.float64)/RATE
            gain=10**(np.interp(timeline,times,gains)/20)
            (source[pos:end]*gain[:,None]).astype('<f4').tofile(f)
            progress('level',end,count)
    del source
    master=out/'master.wav';limit=10**((params['peak_dbtp']-.2)/20)
    filters=f'aresample=192000,alimiter=limit={limit:.9f}:attack=5:release=80:level=false:latency=true,aresample=48000,apad=whole_len={count},atrim=end_sample={count}'
    run(['ffmpeg','-v','error','-f','f32le','-ar',str(RATE),'-ac','2','-i',raw,'-af',filters,'-c:a','pcm_s24le','-rf64','auto','-y',master],cancelled=cancelled)
    progress('peak-check',0,1);peak=measure(master,cancelled=cancelled)['true_peak_dbtp']
    if peak is not None and peak>params['peak_dbtp']+.05:raise ValueError(f'Peak verification failed: {peak} dBTP')
    for i,r in enumerate(rows):
        check_cancel(cancelled);r['after_lufs']=measure(master,r['start'],r['end'],cancelled)['lufs']
        r['deviation_lu']=round(r['after_lufs']-params['target_lufs'],2) if r['after_lufs'] is not None else None
        r['target_met']=not r['excluded'] and r['deviation_lu'] is not None and abs(r['deviation_lu'])<=2
        progress('measure-after',i+1,len(rows))
    previews={}
    for name,path in [('before',analysis['mix_path']),('after',master)]:
        preview=out/f'{name}.wav'
        run(['ffmpeg','-v','error','-i',path,'-c:a','pcm_s16le','-rf64','auto','-y',preview],cancelled=cancelled)
        previews[name+'_preview']=str(preview)
    report=dict(version=1,master=str(master),master_sha256=cards.digest(master),params=params,excluded=excluded,
                samples=count,sample_rate=RATE,channels=2,duration=analysis['duration'],intervals=rows,
                before=statistics(rows,'before_lufs'),after=statistics(rows,'after_lufs'),true_peak_dbtp=peak,
                speech_seconds=analysis['speech_seconds'],exceptions=sum(not r['target_met'] and not r['excluded'] for r in rows),
                source_reconstruction_only=True,editor_render_verified=False,**previews)
    report['file_hashes']={str(master):cards.digest(master),**{path:cards.digest(path) for path in previews.values()}}
    report['analysis_hash']=cards.object_hash(analysis)
    write_json(out/'report.json',report);raw.unlink(missing_ok=True)
    return report
