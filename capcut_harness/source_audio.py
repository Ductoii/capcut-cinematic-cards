"""Speech-anchored source leveling before the timeline summing bus.

Detector conditioning never reaches rendered samples. Independent background
tracks are not modulated by the speech envelope of another source.
"""
import hashlib
from pathlib import Path

import numpy as np

from .audio import parameters, statistics, write_json, envelope
from .legacy import cards
from .loudness import measure
from .mix import RATE, BLOCK, atempo, assert_sources_current
from .process import run, check_cancel
from .quality import evidence
from .speech import detect


def pcm_to_wav(raw, target, count, cancelled, filters=None, codec='pcm_f32le'):
    args=['ffmpeg','-v','error','-f','f32le','-ar',str(RATE),'-ac','2','-i',raw]
    if filters:args+=['-af',filters]
    run([*args,'-ar',str(RATE),'-ac','2','-c:a',codec,'-rf64','auto','-y',target],cancelled=cancelled)


def decode_source(source, directory, cancelled):
    directory.mkdir(parents=True,exist_ok=True)
    count=round(source['end']*RATE)-round(source['start']*RATE)
    raw=directory/'source.f32'
    filters=atempo(source['speed'])+[f'apad=whole_len={count}',f'atrim=end_sample={count}']
    with raw.open('wb') as f:
        run(['ffmpeg','-v','error','-threads','1','-ss',f'{source["source_start"]:.9f}',
             '-t',f'{(source["end"]-source["start"])*source["speed"]:.9f}','-i',source['path'],
             '-map','0:a:0','-vn','-af',','.join(filters),'-ar',str(RATE),'-ac','2','-f','f32le','-'],stdout=f,cancelled=cancelled)
    if raw.stat().st_size!=count*8:raise ValueError('Mapped source duration differs from timeline')
    samples=np.memmap(raw,dtype='<f4',mode='r+',shape=(count,2));peak=0.;hot=0
    try:
        for pos in range(0,count,BLOCK):
            check_cancel(cancelled);end=min(count,pos+BLOCK)
            block=samples[pos:end];hot+=int(np.count_nonzero(np.abs(block)>=.9999))
            times=(round(source['start']*RATE)+np.arange(pos,end))/RATE
            gain=np.full(end-pos,source['volume'],dtype=np.float64)
            for fade in source['envelopes']:
                if fade['fade_in']>0:gain*=np.clip((times-fade['origin'])/fade['fade_in'],0,1)
                if fade['fade_out']>0:gain*=np.clip((fade['origin']+fade['duration']-times)/fade['fade_out'],0,1)
            block[:]=(block*gain[:,None]).astype('<f4');peak=max(peak,float(np.max(np.abs(block),initial=0)))
        samples.flush()
    finally:del samples
    wav=directory/'source.wav';pcm_to_wav(raw,wav,count,cancelled)
    return dict(raw_path=str(raw),wav_path=str(wav),samples=count,peak_amplitude=peak,near_full_scale_samples=hot)


def anchor(rows,key):
    usable=[r for r in rows if not r.get('excluded') and r.get(key) is not None]
    if not usable:return None
    # Duration-weighted median anchors a take without letting one shouted word
    # or an unusually long pause set the gain for all of its normal dialogue.
    ordered=sorted(usable,key=lambda r:r[key]);total=sum(r['end']-r['start'] for r in ordered);n=0.
    for row in ordered:
        n+=row['end']-row['start']
        if n>=total/2:return row[key]


def analyze_sources(inventory,out,params,progress=lambda *a:None,cancelled=lambda:False):
    parameters(params);assert_sources_current(inventory)
    if inventory['issues']:raise ValueError('; '.join(x['reason'] for x in inventory['issues']))
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    count=round(inventory['duration']*RATE);mix_raw=out/'mix.f32'
    with mix_raw.open('wb') as f:f.truncate(count*8)
    bus=np.memmap(mix_raw,dtype='<f4',mode='r+',shape=(count,2));sources=[];intervals=[]
    try:
        for index,source in enumerate(inventory['sources']):
            check_cancel(cancelled)
            identity=source.get('instance_id','/'.join([*source.get('parents',[]),source['id']]))
            key=hashlib.sha256((identity+':'+str(index)).encode()).hexdigest()[:20]
            record={**source,**decode_source(source,out/'sources'/key,cancelled),
                    'source_id':key,'instance_id':identity}
            local=detect(record['wav_path'],out/'sources'/key/'vad',cancelled,conditioning=True)
            for number,span in enumerate(local):
                span.update(id=f'{key}-{number+1:04d}',source_id=key,
                            local_start=span['start'],local_end=span['end'])
                span['before_lufs']=measure(record['wav_path'],span['local_start'],span['local_end'],cancelled)['lufs']
                span['start']+=source['start'];span['end']+=source['start']
                intervals.append(span)
            record['status']='speech' if local else 'no-speech-detected'
            record['interval_ids']=[r['id'] for r in local]
            record['before_lufs']=anchor(local,'before_lufs')
            record['review_flags']=(['no-speech-detected'] if not local else [])+(['low-vad-score'] if any(r['vad_low_score'] for r in local) else [])
            record['raw_sha256']=cards.digest(record['raw_path']);record['wav_sha256']=cards.digest(record['wav_path'])
            samples=np.memmap(record['raw_path'],dtype='<f4',mode='r',shape=(record['samples'],2))
            first=round(source['start']*RATE)
            for pos in range(0,len(samples),BLOCK):
                end=min(len(samples),pos+BLOCK);bus[first+pos:first+end]+=samples[pos:end]
            del samples;sources.append(record);progress('source-analysis',index+1,len(inventory['sources']))
        bus.flush()
    finally:del bus
    assert_sources_current(inventory)
    mix=out/'mix.wav';pcm_to_wav(mix_raw,mix,count,cancelled)
    report=dict(version=2,engine='source-dialogue-v2',sources=sources,intervals=intervals,
                mix_path=str(mix),mix_sha256=cards.digest(mix),raw_path=str(mix_raw),raw_sha256=cards.digest(mix_raw),
                samples=count,sample_rate=RATE,channels=2,duration=count/RATE,
                speech_seconds=round(sum(r['end']-r['start'] for r in intervals),3),
                detector='Silero v6, source-local with analysis-only level conditioning',
                source_quality=[dict(segment_id=s['id'],source_id=s['source_id'],near_full_scale_samples=s['near_full_scale_samples'],
                                     peak_amplitude=s['peak_amplitude'],decoded_samples=s['samples']) for s in sources],
                source_reconstruction_only=True,editor_render_verified=False)
    write_json(out/'analysis.json',report);return report


def render_sources(analysis,out,params,excluded,progress=lambda *a:None,cancelled=lambda:False):
    params=parameters(params);out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    ids={r['id'] for r in analysis['intervals']}
    if not isinstance(excluded,list) or any(i not in ids for i in excluded):raise ValueError('Unknown speech interval exclusion')
    for path,signature in [(analysis['mix_path'],analysis['mix_sha256']),(analysis['raw_path'],analysis['raw_sha256'])]:
        if cards.digest(path)!=signature:raise ValueError('Analyzed audio changed; analyze again')
    rows=[dict(r,excluded=r['id'] in excluded) for r in analysis['intervals']]
    if not any(not r['excluded'] and r['before_lufs'] is not None for r in rows):raise ValueError('No accepted speech to normalize')
    count=analysis['samples'];raw=out/'leveled.f32'
    with raw.open('wb') as f:f.truncate(count*8)
    bus=np.memmap(raw,dtype='<f4',mode='r+',shape=(count,2));source_results=[]
    try:
        for index,source in enumerate(analysis['sources']):
            check_cancel(cancelled)
            for name,signature in [('raw_path','raw_sha256'),('wav_path','wav_sha256')]:
                if cards.digest(source[name])!=source[signature]:raise ValueError('Analyzed source changed')
            directory=out/source['source_id'];directory.mkdir(exist_ok=True)
            accepted=[r for r in rows if r['source_id']==source['source_id'] and not r['excluded'] and r['before_lufs'] is not None]
            own=[r for r in rows if r['source_id']==source['source_id']]
            level=anchor(accepted,'before_lufs');base=float(np.clip(params['target_lufs']-level,-48,params['max_boost_db'])) if level is not None else 0.
            # A gentle, bounded phrase trim complements the take's static gain.
            # Excluded phrases receive no processing, including the static gain.
            segments=[]
            for r in own:
                desired=float(np.clip(params['target_lufs']-r['before_lufs'],-48,params['max_boost_db'])) if r['before_lufs'] is not None and not r['excluded'] else 0.
                gain=base+float(np.clip(desired-base,-3,3)) if not r['excluded'] else 0.
                r['gain_db']=round(gain,3)
                segments.append(dict(start=r['local_start'],end=r['local_end'],gain_db=gain-base))
            times,gains=envelope(segments,source['samples']/RATE) if segments else (np.array([0.]),np.array([0.]))
            # Keep a source's ambience at its take gain, with smooth phrase trims.
            # Sources without accepted dialogue pass through byte-for-byte here.
            samples=np.memmap(source['raw_path'],dtype='<f4',mode='r',shape=(source['samples'],2))
            leveled=directory/'leveled.f32'
            with leveled.open('wb') as f:
                for pos in range(0,len(samples),BLOCK):
                    check_cancel(cancelled);end=min(len(samples),pos+BLOCK)
                    gain=10**((base+np.interp(np.arange(pos,end)/RATE,times,gains))/20)
                    (samples[pos:end]*gain[:,None]).astype('<f4').tofile(f)
            del samples
            corrected=directory/'corrected.wav';compression=bool(accepted)
            if compression:
                # Smooth RMS compression of protruding syllables, with no auto
                # makeup or AGC that would lift silence between sentences.
                filters='acompressor=threshold=0.2511886:ratio=2:attack=15:release=180:knee=2.828:makeup=1:link=average:detection=rms'
                pcm_to_wav(leveled,corrected,source['samples'],cancelled,filters)
                for r in accepted:r['processed_lufs']=measure(corrected,r['local_start'],r['local_end'],cancelled)['lufs']
                processed=anchor(accepted,'processed_lufs')
                makeup=float(np.clip(params['target_lufs']-processed,max(-6.,-48-base),min(6.,params['max_boost_db']-base))) if processed is not None else 0.
                # Per-source transient protection keeps a wild source from
                # becoming the final mix limiter's gain-control signal.
                protected=directory/'protected.wav';limit=10**((params['peak_dbtp']-.2)/20)
                run(['ffmpeg','-v','error','-i',corrected,'-af',f'volume={makeup:.6f}dB,aresample=192000,alimiter=limit={limit:.9f}:attack=5:release=100:level=false:latency=true,aresample=48000,apad=whole_len={source["samples"]},atrim=end_sample={source["samples"]}',
                     '-c:a','pcm_f32le','-rf64','auto','-y',protected],cancelled=cancelled)
                corrected=protected
            else:
                makeup=0.;pcm_to_wav(leveled,corrected,source['samples'],cancelled)
            decoded=directory/'corrected.f32'
            with decoded.open('wb') as f:run(['ffmpeg','-v','error','-i',corrected,'-f','f32le','-'],stdout=f,cancelled=cancelled)
            part=np.memmap(decoded,dtype='<f4',mode='r+',shape=(source['samples'],2));first=round(source['start']*RATE)
            excluded_rows=[r for r in own if r['excluded']]
            if excluded_rows:
                original=np.memmap(source['raw_path'],dtype='<f4',mode='r',shape=(source['samples'],2))
                for row in excluded_rows:
                    left=round(row['local_start']*RATE);right=min(source['samples'],round(row['local_end']*RATE))
                    part[left:right]=original[left:right]
                part.flush();del original
            for pos in range(0,len(part),BLOCK):
                check_cancel(cancelled);end=min(len(part),pos+BLOCK);bus[first+pos:first+end]+=part[pos:end]
            del part
            for r in own:
                r['isolated_after_lufs']=r['before_lufs'] if r['excluded'] else measure(corrected,r['local_start'],r['local_end'],cancelled)['lufs']
                r['gain_db']=round(r['gain_db']+makeup,3) if not r['excluded'] else 0.
            source_results.append(dict(source_id=source['source_id'],segment_id=source['id'],instance_id=source['instance_id'],
                path=source['path'],start=source['start'],end=source['end'],status='leveled' if accepted else ('excluded' if own else 'no-speech-detected'),
                before_lufs=level,after_lufs=anchor(accepted,'isolated_after_lufs'),gain_db=round(base+makeup,3),
                compression='gentle-rms-2:1' if compression else 'none',review_flags=source['review_flags'],
                large_correction=abs(base+makeup)>18))
            for p in (leveled,decoded,*(directory.glob('*.wav'))):p.unlink(missing_ok=True)
            progress('source-level',index+1,len(analysis['sources']))
        bus.flush()
    finally:del bus
    master=out/'master.wav';limit=10**((params['peak_dbtp']-.2)/20)
    filters=f'aresample=192000,alimiter=limit={limit:.9f}:attack=5:release=100:level=false:latency=true,aresample=48000,apad=whole_len={count},atrim=end_sample={count}'
    pcm_to_wav(raw,master,count,cancelled,filters,'pcm_s24le')
    master_level=measure(master,cancelled=cancelled);peak=master_level['true_peak_dbtp']
    if peak is None or peak>params['peak_dbtp']+.05:raise ValueError('Rendered master exceeds the requested peak ceiling')
    for index,r in enumerate(rows):
        check_cancel(cancelled);r['after_lufs']=measure(master,r['start'],r['end'],cancelled)['lufs']
        r['deviation_lu']=round(r['after_lufs']-params['target_lufs'],2) if r['after_lufs'] is not None else None
        r['overlapping_sources']=sum(s['start']<r['end'] and s['end']>r['start'] for s in analysis['sources'])>1
        r['target_met']=not r['excluded'] and r['deviation_lu'] is not None and abs(r['deviation_lu'])<=2
        progress('measure-after',index+1,len(rows))
    quality=evidence(analysis,raw,master,out,rows,cancelled)
    no_speech=[s['source_id'] for s in source_results if s['status']=='no-speech-detected']
    quality['unresolved_sources']=no_speech
    if no_speech:quality['flags'].append('sources-without-detected-speech')
    previews={}
    for name,path in [('before',analysis['mix_path']),('after',master)]:
        preview=out/f'{name}.wav';run(['ffmpeg','-v','error','-i',path,'-c:a','pcm_s16le','-rf64','auto','-y',preview],cancelled=cancelled);previews[name+'_preview']=str(preview)
    report=dict(version=2,engine='source-dialogue-v2',preset='Online film dialogue',master=str(master),master_sha256=cards.digest(master),
        params=params,excluded=excluded,samples=count,sample_rate=RATE,channels=2,duration=count/RATE,intervals=rows,
        sources=source_results,source_coverage=dict(total=len(source_results),leveled=sum(s['status']=='leveled' for s in source_results),
        excluded=sum(s['status']=='excluded' for s in source_results),no_speech_detected=len(no_speech)),
        before=statistics(rows,'before_lufs'),after=statistics(rows,'after_lufs'),true_peak_dbtp=peak,programme_lufs=master_level['lufs'],
        speech_seconds=analysis['speech_seconds'],exceptions=sum(not r['target_met'] and not r['excluded'] for r in rows),quality=quality,
        source_reconstruction_only=True,editor_render_verified=False,**previews)
    report['file_hashes']={str(master):cards.digest(master),**{path:cards.digest(path) for path in previews.values()}}
    report['analysis_hash']=cards.object_hash(analysis);write_json(out/'report.json',report);raw.unlink(missing_ok=True)
    return report
