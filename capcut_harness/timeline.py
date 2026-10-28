"""Strict audio mapping; unsupported audible semantics are explicit blockers."""
import json
import math
import re
from pathlib import Path

from .legacy import cards
from .process import run


def stream_info(path):
    raw,_=run(['ffprobe','-v','error','-select_streams','a','-show_entries',
               'stream=index,sample_rate,channels,channel_layout:format=duration','-of','json',path],timeout=30)
    return json.loads(raw)


def inspect_audio(project):
    project,active,data,mirrors,signature=cards.load(project)
    if any(t.get('name','').startswith('Harness · Dialogue') for t in data['tracks']):
        raise ValueError('Project already contains a harness audio master; undo its job before re-analysis')
    sources=[];issues=[];separated=0;cache={};source_hashes={}

    def issue(ident,reason):
        issues.append(dict(segment_id=ident,reason=reason))

    def walk(draft,offset,scale,bounds,parents,gain=1.,envelopes=()):
        nonlocal separated
        if len(parents)>12:
            issue('/'.join(parents),'Compound nesting exceeds 12');return
        materials={m.get('id'):(kind,m) for kind,values in draft.get('materials',{}).items()
                   if isinstance(values,list) for m in values if isinstance(m,dict)}
        for track in draft.get('tracks',[]):
            if track.get('type') not in ('audio','video') or track.get('is_muted') or track.get('muted'):
                continue
            for segment in track.get('segments',[]):
                ident=segment.get('id','unknown')
                if not segment.get('visible',True) or segment.get('is_muted') or segment.get('muted'):
                    continue
                tr=segment.get('target_timerange') or {};ts=tr.get('start',0)/1e6;td=tr.get('duration',0)/1e6
                if td<=0:continue
                left=max(bounds[0],offset+ts*scale);right=min(bounds[1],offset+(ts+td)*scale)
                if right<=left:continue
                volume=float(segment.get('volume',1))*gain
                if not math.isfinite(volume) or volume<0:
                    issue(ident,'Invalid volume');continue
                if not volume:continue
                kind,material=materials.get(segment.get('material_id'),('',{}))
                refs=[materials[x] for x in segment.get('extra_material_refs',[]) if x in materials]
                nested=[m for k,m in refs if k=='drafts']
                if kind=='drafts':nested.append(material)
                if not nested and kind not in ('videos','audios'):
                    continue
                if kind=='videos' and not nested and material.get('has_sound_separated'):
                    separated+=1;continue
                if kind=='videos' and material.get('type') in ('photo','image'):
                    continue
                problems=[]
                if track.get('flag',0) or track.get('attribute',0):problems.append('Unsupported track flags')
                if segment.get('reverse') or segment.get('is_loop'):problems.append('Unsupported reverse/loop')
                if segment.get('intensifies_audio') or segment.get('is_tone_modify'):problems.append('Unsupported audio enhancement/pitch processing')
                if segment.get('keyframe_refs') or any(k.get('property_type') in ('KFTypeVolume','KFTypeAudioVolume') for k in segment.get('common_keyframes',[])):
                    problems.append('Unsupported audio keyframe')
                fades=list(envelopes)
                for ref_kind,m in refs:
                    if ref_kind=='speeds' and m.get('curve_speed'):problems.append('Unsupported curve speed')
                    if ref_kind=='audio_fades':
                        if m.get('fade_type',0)!=0:problems.append('Unsupported audio fade curve')
                        else:fades.append(dict(origin=offset+ts*scale,duration=td*scale,
                                               fade_in=m.get('fade_in_duration',0)/1e6*scale,
                                               fade_out=m.get('fade_out_duration',0)/1e6*scale))
                    if ref_kind=='sound_channel_mappings' and (m.get('audio_channel_mapping',0)!=0 or m.get('is_config_open',False)):
                        problems.append('Unsupported sound channel routing')
                    if ref_kind=='vocal_separations' and (m.get('choice',0)!=0 or m.get('production_path') or m.get('removed_sounds')):
                        problems.append('Unsupported vocal separation')
                    if ref_kind in ('audio_effects','audio_balances','audio_pannings','audio_pitch_shifts','audio_track_indexes'):
                        problems.append(f'Unsupported {ref_kind}')
                    if ref_kind=='effects' and m.get('type') not in ('sharpen','particle','lut','hsl','brightness','contrast','saturation','temperature','vignette','fade','exposure','filter'):
                        problems.append(f'Unclassified effect {m.get("type")}')
                    if ref_kind=='transitions' and (m.get('audio_effect') or m.get('is_audio') or m.get('type') in ('audio_transition','audio')):
                        problems.append('Unsupported audio transition')
                if problems:
                    for problem in dict.fromkeys(problems):issue(ident,problem)
                    continue
                sr=segment.get('source_timerange') or dict(start=0,duration=td*1e6)
                ss=sr.get('start',0)/1e6;sd=sr.get('duration',td*1e6)/1e6
                if sd<=0:issue(ident,'Invalid source duration');continue
                speed=sd/(td*scale)
                if nested:
                    if len(nested)!=1 or not isinstance(nested[0].get('draft'),dict):
                        issue(ident,'Ambiguous/external compound');continue
                    child_scale=scale*td/sd
                    walk(nested[0]['draft'],offset+ts*scale-ss*child_scale,child_scale,
                         (left,right),parents+[ident],volume,tuple(fades))
                    continue
                raw=material.get('path','')
                if not raw:issue(ident,'Missing audio media path');continue
                raw=re.sub(r'^##_draftpath_placeholder_[^/\\]+_##[/\\]','',raw)
                path=Path(raw).expanduser();path=path if path.is_absolute() else project/path
                if not path.is_file():issue(ident,f'Missing source media: {path.name}');continue
                path=path.resolve()
                if path not in cache:
                    try:cache[path]=stream_info(path)
                    except (ValueError,OSError) as exc:cache[path]={'error':str(exc)}
                meta=cache[path]
                if meta.get('error'):issue(ident,meta['error']);continue
                if not meta.get('streams'):continue
                if len(meta['streams'])!=1 or meta['streams'][0].get('channels',0)>2:
                    issue(ident,'Only one mono/stereo audio stream is supported');continue
                position=ss+(left-(offset+ts*scale))*speed
                if position < -.00001:issue(ident,'Negative source seek');continue
                media_duration=float(meta.get('format',{}).get('duration',0) or 0)
                if media_duration and position+(right-left)*speed>media_duration+.06:
                    issue(ident,'Source trim exceeds media duration');continue
                instance='/'.join([*parents,ident])
                sources.append(dict(id=ident,instance_id=instance,path=str(path),kind=kind,start=left,end=right,
                                    source_start=max(0,position),speed=speed,volume=volume,
                                    envelopes=fades,parents=parents,root_id=(parents[0] if parents else ident)))

    walk(data,0.,1.,(0.,data['duration']/1e6),[])
    for path in {s['path'] for s in sources}:source_hashes[path]=cards.digest(path)
    if cards.digest(active)!=signature:raise ValueError('Project changed during audio inspection')
    guards=dict((name,cards.digest(project/name)) for name in mirrors)
    for name in ('Timelines/project.json',cards.STATE):
        guards[name]=cards.digest(project/name)
    return dict(project=str(project),project_id=data.get('id'),project_sha256=signature,
                duration=data['duration']/1e6,duration_us=data['duration'],fps=data['fps'],
                mirrors=mirrors,guards=guards,source_hashes=source_hashes,
                sources=sorted(sources,key=lambda s:(s['start'],s['id'])),issues=issues,
                root_mute_ids=sorted({s['root_id'] for s in sources}),
                separated_video_count=separated,source_reconstruction_only=True,editor_render_verified=False)
