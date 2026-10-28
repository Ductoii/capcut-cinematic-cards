"""Journaled native audio transactions sharing the cards tool's project lock."""
import copy
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from .legacy import cards
from .mix import assert_sources_current
from .audio import write_json

STATE='.capcut-harness-audio.json'


def atomic_copy(target,source):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.harness-'+uuid.uuid4().hex+'.part')
    try:
        with Path(source).open('rb') as src,temporary.open('xb') as dst:
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)


def safe_target(project,name):
    path=Path(name)
    parts=path.parts
    mirror=(len(parts)==1 or (len(parts)==3 and parts[0]=='Timelines' and re.fullmatch(r'[A-Za-z0-9_-]+',parts[1]))) and parts[-1] in ('draft_info.json','draft_info.json.bak','template-2.tmp')
    resource=bool(re.fullmatch(r'Resources/HarnessAudio/[a-f0-9]{32}\.wav',name))
    cards.require(name==STATE or mirror or resource,'Unsafe harness transaction target')
    cards.require(not path.is_absolute() and '..' not in parts,'Unsafe transaction path')
    target=project/path
    cards.require(target.resolve().is_relative_to(project),'Transaction path escapes project')
    for part in [target,*target.parents]:
        if part==project.parent:break
        cards.require(not part.is_symlink(),'Symlinked transaction target')
    return target


def stage(inventory,rendered,directory):
    assert_sources_current(inventory)
    project,_,original,mirrors,signature=cards.load(inventory['project'])
    cards.require(not (project/STATE).exists(),'Project already has a harness audio transaction; undo first')
    directory=Path(directory).resolve()
    cards.require(not directory.exists() and not directory.is_relative_to(project),'Use a fresh stage outside the project')
    master=Path(rendered['master']).resolve(strict=True)
    cards.require(cards.digest(master)==rendered['master_sha256'],'Master changed since review')
    cards.require(rendered['samples']==round(inventory['duration']*48000),'Master duration differs from project')
    cards.require(rendered.get('true_peak_dbtp') is not None and rendered['true_peak_dbtp']<=rendered['params']['peak_dbtp']+.05,'Unverified master true peak')
    result=copy.deepcopy(original);ident=uuid.uuid4().hex
    resource=f'Resources/HarnessAudio/{ident}.wav'
    cards.require(not safe_target(project,resource).exists(),'Resource collision')
    muted=[]
    for track in result['tracks']:
        if track['type'] in ('audio','video'):
            for s in track.get('segments',[]):
                if s.get('id') in inventory['root_mute_ids']:
                    muted.append(s['id']);s['volume']=0.
    cards.require(set(muted)==set(inventory['root_mute_ids']),'Audible root segment changed')
    duration=original['duration'];mid=str(uuid.uuid4()).upper();sid=str(uuid.uuid4()).upper();tid=str(uuid.uuid4()).upper()
    material=dict(id=mid,type='extract_music',name='Dialogue master.wav',material_name='Dialogue master.wav',
                  path=str(project/resource),duration=duration,category_name='local',source_platform=0,
                  wave_points=[],music_id='',app_id=0,resource_id='',effect_id='',local_material_id=ident,
                  check_flag=1,team_id='',text_id='',tone_type='',formula_id='',is_ugc=False,
                  intensifies_path='',video_id='',third_resource_id='',category_id='')
    native=dict(id=sid,material_id=mid,source_timerange=dict(start=0,duration=duration),
                target_timerange=dict(start=0,duration=duration),render_timerange=dict(start=0,duration=0),
                extra_material_refs=[],common_keyframes=[],keyframe_refs=[],volume=1.,last_nonzero_volume=1.,
                speed=1.,visible=True,reverse=False,is_loop=False,is_tone_modify=False,intensifies_audio=False,
                cartoon=False,clip=None,uniform_scale=None,render_index=0,track_render_index=len(result['tracks']),
                track_attribute=0,enable_lut=False,enable_adjust=False,group_id='',state=0,source='segmentsourcenormal')
    result['materials'].setdefault('audios',[]).append(material)
    result['tracks'].append(dict(id=tid,type='audio',name='Harness · Dialogue master',attribute=0,flag=0,segments=[native]))
    # Strict preservation proof: remove only the new objects and restore only root volume.
    check=copy.deepcopy(result);check['tracks'].pop();check['materials']['audios'].pop()
    if 'audios' not in original['materials']:check['materials'].pop('audios')
    for old,new in zip(original['tracks'],check['tracks']):
        for a,b in zip(old.get('segments',[]),new.get('segments',[])):
            if a.get('id') in muted:
                if 'volume' in a:b['volume']=a['volume']
                else:b.pop('volume',None)
    cards.require(check==original,'Audio stage changed unrelated project content')
    directory.mkdir(parents=True);(directory/'before').mkdir()
    draft_path=directory/'draft.json';draft_path.write_bytes(cards.encoded(result))
    state=dict(version=1,transaction=str(directory),resource=resource,track_id=tid,master_sha256=rendered['master_sha256'])
    write_json(directory/'state.json',state);write_json(directory/'review.json',rendered)
    before={};after={};files={}
    # Asset first, draft mirrors next, ownership last. Every partial state is recoverable.
    order=[resource,*mirrors,STATE]
    for name in order:
        target=safe_target(project,name);before[name]=cards.digest(target)
        if target.exists():atomic_copy(directory/'before'/name,target)
        source=master if name==resource else directory/('state.json' if name==STATE else 'draft.json')
        files[name]=str(source);after[name]=cards.digest(source)
    meta=dict(version=1,project=str(project),project_id=original.get('id'),before=before,after=after,files=files,
              guards={k:v for k,v in inventory['guards'].items() if k not in mirrors},
              evidence={**inventory['source_hashes'],**rendered['file_hashes'],str(directory/'review.json'):cards.digest(directory/'review.json')},
              resource=resource,original_object_hash=cards.object_hash(original),preservation_verified=True,
              editor_render_verified=False)
    write_json(directory/'transaction.json',meta);write_json(directory/'journal.json',dict(state='staged',written=[]))
    return directory


def transaction(directory):
    directory=Path(directory).resolve(strict=True);meta=cards.read(directory/'transaction.json')
    cards.require(meta.get('version')==1,'Unsupported harness transaction')
    project=Path(meta['project']).resolve(strict=True)
    cards.require(set(meta['before'])==set(meta['after'])==set(meta['files']),'Incomplete harness transaction')
    for name,signature in meta['after'].items():
        safe_target(project,name)
        src=Path(meta['files'][name])
        cards.require(not src.is_symlink() and cards.digest(src)==signature,'Staged output changed: integrity failure')
        if name!=meta['resource']:
            cards.require(src==directory/('state.json' if name==STATE else 'draft.json'),'Unsafe staged draft path')
        if meta['before'][name] is not None:
            cards.require(cards.digest(directory/'before'/name)==meta['before'][name],'Backup changed: integrity failure')
    return directory,project,meta


def check_evidence(project,meta):
    for name,signature in meta['evidence'].items():
        cards.require(cards.digest(name)==signature,'Source media or reviewed output changed; regenerate job')
    for name,signature in meta['guards'].items():
        cards.require(name in ('Timelines/project.json',cards.STATE),'Unsafe project guard')
        cards.require(cards.digest(project/name)==signature,'Project state changed since review')


def verify(directory):
    directory,project,meta=transaction(directory)
    for name,signature in meta['after'].items():
        cards.require(cards.digest(safe_target(project,name))==signature,f'Output changed: {name}')
    return dict(verified=True,project=str(project),file_verification_only=True,
                preservation_verified=meta['preservation_verified'],editor_render_verified=False)


def apply(directory):
    directory,project,meta=transaction(directory)
    cards.require(not cards.editor_running(),'CapCut is running; save and close before apply')
    check_evidence(project,meta)
    with cards.locked(project):
        if all(cards.digest(project/n)==v for n,v in meta['after'].items()):return verify(directory)
        for name,previous in meta['before'].items():
            cards.require(cards.digest(safe_target(project,name)) in (previous,meta['after'][name]),f'Project changed since staging: {name}')
        written=[]
        try:
            for name,previous in meta['before'].items():
                cards.require(not cards.editor_running(),'CapCut started during apply; rolling back')
                target=safe_target(project,name);current=cards.digest(target)
                cards.require(current in (previous,meta['after'][name]),f'Project changed during apply: {name}')
                if current==meta['after'][name]:continue
                atomic_copy(target,meta['files'][name]);written.append(name)
                write_json(directory/'journal.json',dict(state='applying',written=written))
            result=verify(directory);write_json(directory/'journal.json',dict(state='applied',written=written));return result
        except BaseException:
            # Also restore known partial writes from a prior interrupted invocation.
            for name in reversed(list(meta['before'])):
                target=safe_target(project,name)
                if cards.digest(target)==meta['after'][name]:
                    if meta['before'][name] is None:target.unlink(missing_ok=True)
                    else:atomic_copy(target,directory/'before'/name)
            write_json(directory/'journal.json',dict(state='apply-failed',written=written));raise


def undo(directory):
    directory,project,meta=transaction(directory)
    cards.require(not cards.editor_running(),'CapCut is running; save and close before undo')
    with cards.locked(project):
        for name,old in meta['before'].items():
            cards.require(cards.digest(safe_target(project,name)) in (old,meta['after'][name]),f'Project changed after apply: {name}; preserving user edits')
        for name in reversed(list(meta['before'])):
            if name==meta['resource']:continue
            cards.require(not cards.editor_running(),'CapCut started during undo; close and retry')
            target=safe_target(project,name);old=meta['before'][name]
            cards.require(cards.digest(target) in (old,meta['after'][name]),'Project changed during undo')
            if cards.digest(target)==old:continue
            if old is None:target.unlink(missing_ok=True)
            else:atomic_copy(target,directory/'before'/name)
        cards.require(all(n==meta['resource'] or cards.digest(project/n)==v for n,v in meta['before'].items()),'Undo verification failed')
        write_json(directory/'journal.json',dict(state='restored',written=[]))
    return dict(restored=True,project=str(project),editor_render_verified=False)
