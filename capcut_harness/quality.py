"""Bounded audio-quality evidence; flags do not claim to identify distortion or singers."""
from pathlib import Path
import numpy as np
from .mix import RATE,BLOCK
from .process import run,check_cancel


def mix_levels(raw,cancelled):
    audio=np.memmap(raw,dtype='<f4',mode='r');count=0;peak=0.
    try:
        for pos in range(0,len(audio),BLOCK*2):
            check_cancel(cancelled);amplitude=np.abs(audio[pos:pos+BLOCK*2])
            count+=int(np.count_nonzero(amplitude>=.9999));peak=max(peak,float(np.max(amplitude)))
    finally:del audio
    return dict(mix_full_scale_samples=count,mix_peak_amplitude=peak,near_full_scale_threshold=.9999)


def evidence(analysis,leveled,master,out,rows,cancelled):
    result=mix_levels(analysis['raw_path'],cancelled)
    decoded=Path(out)/'quality-master.f32'
    try:
        with decoded.open('wb') as f:run(['ffmpeg','-v','error','-i',master,'-f','f32le','-'],stdout=f,cancelled=cancelled)
        before=np.memmap(leveled,dtype='<f4',mode='r').reshape(-1,2)
        after=np.memmap(decoded,dtype='<f4',mode='r').reshape(-1,2)
        if len(before)!=len(after):raise ValueError('Quality-check duration differs from rendered master')
        total=active=0;maximum=0.;window=960
        for pos in range(0,len(before),BLOCK):
            check_cancel(cancelled);end=min(pos+BLOCK,len(before));n=(end-pos)//window
            if not n:continue
            left=np.asarray(before[pos:pos+n*window],dtype=np.float64).reshape(n,-1)
            right=np.asarray(after[pos:pos+n*window],dtype=np.float64).reshape(n,-1)
            a=np.sqrt(np.mean(left*left,axis=1));b=np.sqrt(np.mean(right*right,axis=1))
            reduction=np.where(a>1e-5,20*np.log10(np.maximum(a,1e-12)/np.maximum(b,1e-12)),0.)
            total+=n;active+=int(np.count_nonzero(reduction>.5));maximum=max(maximum,float(np.max(reduction)))
        del before,after
    finally:decoded.unlink(missing_ok=True)
    source=analysis.get('source_quality')
    low=[r['id'] for r in rows if r.get('vad_low_score') and not r['excluded']]
    result.update(source_quality=source,source_clipping_assessment='decoded-near-full-scale-only' if source is not None else 'unassessed',
        vad_low_score_intervals=low,vad_score_assessment='heuristic mean <0.65 or active fraction <0.6; not calibrated confidence',
        limiter=dict(window_seconds=.02,threshold_db=.5,compared_windows=total,attenuated_windows=active,max_rms_attenuation_db=round(maximum,3),
                     measurement='20ms RMS attenuation between leveled float mix and limited master; not internal limiter gain'),
        music_vocal_classification='unassessed',target_deviations=sum(not r['target_met'] and not r['excluded'] for r in rows))
    result['flags']=([name for name,condition in [('mix-near-full-scale',result['mix_full_scale_samples']>0),('low-vad-score',bool(low)),
        ('decoded-source-near-full-scale',source is not None and any(s['near_full_scale_samples'] for s in source)),
        ('limiter-attenuation',active>0),('target-deviation',result['target_deviations']>0)] if condition])
    return result
