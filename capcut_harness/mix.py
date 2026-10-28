"""Reconstruct supported timeline audio with a disk-backed float summing bus."""
import os
from pathlib import Path

import numpy as np

from .legacy import cards
from .process import run,check_cancel

RATE=48000
BLOCK=RATE*10


def atempo(speed):
    filters=[]
    while speed>2:filters.append('atempo=2');speed/=2
    while speed<.5:filters.append('atempo=0.5');speed*=2
    return filters+[f'atempo={speed:.12g}']


def assert_sources_current(info):
    for name,signature in info['guards'].items():
        if cards.digest(Path(info['project'])/name)!=signature:
            raise ValueError(f'Project changed: {name}')
    for name,signature in info['source_hashes'].items():
        if cards.digest(name)!=signature:raise ValueError('Source media changed since inspection')


def render_mix(inventory,out,progress=lambda *a:None,cancelled=lambda:False):
    if inventory['issues']:raise ValueError('; '.join(f'{x["segment_id"]}: {x["reason"]}' for x in inventory['issues']))
    check_cancel(cancelled);assert_sources_current(inventory)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    count=round(inventory['duration']*RATE)
    raw=out/'mix.f32'
    with raw.open('wb') as f:f.truncate(count*2*4)
    mixed=np.memmap(raw,dtype='<f4',mode='r+',shape=(count,2))
    sources=inventory['sources']
    try:
        for index,source in enumerate(sources):
            check_cancel(cancelled)
            temporary=out/'decode.f32'
            first=round(source['start']*RATE);last=min(count,round(source['end']*RATE));n=last-first
            filters=atempo(source['speed'])+[f'apad=whole_len={n}',f'atrim=end_sample={n}']
            with temporary.open('wb') as handle:
                run(['ffmpeg','-v','error','-threads','1','-ss',f'{source["source_start"]:.9f}',
                     '-t',f'{(source["end"]-source["start"])*source["speed"]:.9f}',
                     '-i',source['path'],'-map','0:a:0','-vn','-af',','.join(filters),
                     '-ar',str(RATE),'-ac','2','-f','f32le','-'],stdout=handle,cancelled=cancelled)
            decoded=np.memmap(temporary,dtype='<f4',mode='r').reshape(-1,2)
            if len(decoded)!=n:raise ValueError('Decoder produced an unexpected sample count')
            for pos in range(0,n,BLOCK):
                check_cancel(cancelled);end=min(n,pos+BLOCK)
                times=np.arange(first+pos,first+end,dtype=np.float64)/RATE
                gain=np.full(end-pos,source['volume'],dtype=np.float64)
                for e in source['envelopes']:
                    if e['fade_in']>0:gain*=np.clip((times-e['origin'])/e['fade_in'],0,1)
                    if e['fade_out']>0:gain*=np.clip((e['origin']+e['duration']-times)/e['fade_out'],0,1)
                mixed[first+pos:first+end]+=decoded[pos:end]*gain[:,None]
            del decoded;temporary.unlink(missing_ok=True)
            progress('mix',index+1,len(sources))
        mixed.flush()
    finally:
        del mixed
        (out/'decode.f32').unlink(missing_ok=True)
    assert_sources_current(inventory)
    target=out/'mix.wav'
    run(['ffmpeg','-v','error','-f','f32le','-ar',str(RATE),'-ac','2','-i',raw,
         '-c:a','pcm_f32le','-rf64','auto','-y',target],cancelled=cancelled)
    return dict(path=str(target),raw_path=str(raw),samples=count,sample_rate=RATE,channels=2,
                source_count=len(sources),source_reconstruction_only=True,editor_render_verified=False)
