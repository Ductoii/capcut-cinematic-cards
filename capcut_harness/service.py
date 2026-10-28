"""Capability registry and persisted single-worker project jobs."""
import copy
import hashlib
import json
import queue
import threading
import time
import uuid
from pathlib import Path

from .actions import parse_command,CAPABILITIES
from .jobs import JobStore,now
from .legacy import cards
from .timeline import inspect_audio
from .mix import render_mix,assert_sources_current
from .audio import analyze,render,parameters,write_json
from . import transaction


class Service:
    def __init__(self,state_dir,project_roots=None):
        self.store=JobStore(state_dir);self.root=self.store.root;self.lock=threading.RLock()
        self.registry=cards.read(self.root/'projects.json') if (self.root/'projects.json').exists() else {}
        self.requests=cards.read(self.root/'requests.json') if (self.root/'requests.json').exists() else {}
        self.queue=queue.Queue();self.stop=threading.Event();self.cancel_events={};self.closed=False
        roots=cards.project_roots() if project_roots is None else project_roots
        for root in roots:
            root=Path(root).expanduser()
            if root.is_dir():
                candidates=[root] if (root/'draft_info.json').exists() else list(root.iterdir())
                for project in candidates:
                    if (project/'draft_info.json').is_file():
                        try:self.register(project)
                        except (ValueError,OSError):pass
        self.worker=threading.Thread(target=self._worker,name='capcut-harness-jobs',daemon=True);self.worker.start()

    def register(self,path):
        project,_,data,_,_=cards.load(Path(path))
        ident=hashlib.sha256(str(project).encode()).hexdigest()[:16]
        with self.lock:
            record={**self.registry.get(ident,{}),**dict(id=ident,name=project.name,path=str(project),duration=data['duration']/1e6,schema=data['version'])}
            self.registry[ident]=record;self.store.write(self.root/'projects.json',self.registry)
        return copy.deepcopy(record)

    def projects(self):
        with self.lock:return sorted(copy.deepcopy(list(self.registry.values())),key=lambda p:p['name'].casefold())

    def _project(self,ident):
        with self.lock:
            if ident not in self.registry:raise ValueError('Unknown project')
            return copy.deepcopy(self.registry[ident])

    def inspect(self,project_id):
        record=self._project(project_id);info=cards.inspect(record['path'])
        info.update(id=project_id,name=record['name'],editor_running=cards.editor_running())
        # Existing native text is displayed as data, never inferred from a face.
        _,_,data,_,_=cards.load(record['path']);texts={m['id']:m for m in data['materials'].get('texts',[])}
        info['cards']=[]
        for track in data['tracks']:
            if track['type']=='text':
                for segment in track.get('segments',[]):
                    material=texts.get(segment.get('material_id'),{})
                    try:text=json.loads(material.get('content','{}')).get('text',material.get('name',''))
                    except (ValueError,TypeError):text=material.get('name','')
                    info['cards'].append(dict(track=track.get('name',''),text=text,range=segment.get('target_timerange')))
        return info

    def jobs(self):
        return sorted([self.store.get(i) for i in list(self.store.records)],key=lambda j:j.get('created_at',''),reverse=True)

    def job(self,ident):
        item=self.store.get(ident)
        if item.get('report_path'):
            item['report']=cards.read(item['report_path'])
        return item

    def command(self,text,project_id=None):
        return self.dispatch(parse_command(text,self.projects(),project_id))

    def dispatch(self,action):
        if not isinstance(action,dict):raise ValueError('Action must be an object')
        action=copy.deepcopy(action);request=action.pop('request_id',None)
        if request is not None and (not isinstance(request,str) or not 1<=len(request)<=100):raise ValueError('Invalid request id')
        fingerprint=cards.object_hash(action)
        with self.lock:
            if request in self.requests:
                saved=self.requests[request]
                if saved['hash']!=fingerprint:raise ValueError('Request id reused with different input')
                return copy.deepcopy(saved['result'])
            result=self._dispatch(action)
            if request is not None:
                self.requests[request]=dict(hash=fingerprint,result=result)
                self.store.write(self.root/'requests.json',self.requests)
            return result

    def _dispatch(self,a):
        name=a.get('action')
        if name=='project.register':return self.register(a['path'])
        if name in ('project.inspect','cards.inspect'):return self.inspect(a['project_id'])
        if name=='dialogue.cancel':
            job=self.store.get(a['job_id'])
            if job['state'] not in ('queued','running') or job.get('operation') not in ('analyze','render'):
                raise ValueError('Only queued/running audio preparation can be cancelled')
            self.cancel_events.setdefault(job['id'],threading.Event()).set()
            return dict(job_id=job['id'],cancel_requested=True)
        if name=='dialogue.retry':
            old=self.store.get(a['job_id'])
            if old['state'] not in ('failed','cancelled','interrupted'):raise ValueError('Retry requires an unfinished/failed job')
            return self._new('analyze',old['project_id'],old.get('params',{}))
        if name=='dialogue.analyze':return self._new('analyze',a['project_id'],parameters(a.get('params',{})))
        if name=='dialogue.render':
            old=self.store.get(a['job_id'])
            if old['state']!='ready':raise ValueError('Render requires a ready analysis')
            return self._new('render',old['project_id'],parameters(a.get('params',old['params'])),parent=old['id'],excluded=a.get('excluded',[]))
        if name in ('dialogue.apply','dialogue.undo'):
            job=self.store.get(a['job_id']);operation=name.split('.')[1]
            required='ready' if operation=='apply' else 'applied'
            if job['state']==('applied' if operation=='apply' else 'restored'):return dict(job_id=job['id'],unchanged=True)
            if job['state']!=required:raise ValueError(f'{operation} requires a {required} job')
            if operation=='apply' and self._project(job['project_id']).get('latest_job')!=job['id']:
                raise ValueError('Newer review revision exists; apply that revision')
            self.store.update(job['id'],state='queued',operation=operation,error=None,error_type=None)
            self.queue.put((job['id'],operation));return dict(job_id=job['id'],queued=True)
        if name in ('cards.stage','cards.apply','cards.verify','cards.restore'):
            if name=='cards.stage':
                project=self._project(a['project_id']);directory=self.root/'card-stages'/uuid.uuid4().hex
                cards.stage(project['path'],a['plan'],directory,Path(a['font']) if a.get('font') else cards.choose_font())
                return dict(stage_id=directory.name)
            stage_id=a.get('stage_id','')
            if not isinstance(stage_id,str) or len(stage_id)!=32 or any(c not in '0123456789abcdef' for c in stage_id):raise ValueError('Invalid card stage')
            directory=self.root/'card-stages'/stage_id
            return getattr(cards,name.split('.')[1])(directory)
        raise ValueError('Unknown action')

    def _new(self,operation,project_id,params,parent=None,excluded=None):
        project=self._project(project_id)
        ident=uuid.uuid4().hex
        job=dict(id=ident,action='dialogue.'+operation,operation=operation,state='queued',project_id=project_id,
                 project_name=project['name'],params=params,parent=parent,excluded=excluded or [],created_at=now(),updated_at=now(),
                 error=None,error_type=None,progress=dict(stage='queued',done=0,total=0))
        self.cancel_events[ident]=threading.Event();self.store.save(job)
        self.registry[project_id]['latest_job']=ident;self.store.write(self.root/'projects.json',self.registry)
        self.queue.put((ident,operation));return dict(job_id=ident,queued=True)

    def _worker(self):
        while not self.stop.is_set():
            try:ident,operation=self.queue.get(timeout=.1)
            except queue.Empty:continue
            job=self.store.get(ident);cancel=self.cancel_events.setdefault(ident,threading.Event())
            state={'apply':'applying','undo':'restoring'}.get(operation,'running')
            self.store.update(ident,state=state,error=None,error_type=None)
            last=[0.]
            def progress(stage,done,total):
                stamp=time.monotonic()
                if stamp-last[0]>=.2 or done==total:
                    self.store.update(ident,progress=dict(stage=stage,done=done,total=total));last[0]=stamp
            try:
                result=self._execute(job,operation,progress,cancel.is_set)
                self.store.update(ident,**result)
            except InterruptedError as exc:self.store.update(ident,state='cancelled',error=str(exc),error_type='cancelled')
            except Exception as exc:
                message=str(exc);error_type='editor_busy' if 'CapCut' in message else ('stale' if 'changed' in message else 'failed')
                fallback={'apply':'ready','undo':'applied'}.get(operation,'failed')
                self.store.update(ident,state=fallback,error=message,error_type=error_type)
            finally:self.queue.task_done()

    def _execute(self,job,operation,progress,cancelled):
        directory=self.root/'jobs'/job['id'];project=self._project(job['project_id'])
        if operation=='apply':
            result=transaction.apply(Path(job['stage_path']));return dict(state='applied',verification=result)
        if operation=='undo':
            result=transaction.undo(Path(job['stage_path']));return dict(state='restored',verification=result)
        if operation=='analyze':
            progress('inspect',0,1);inventory=inspect_audio(project['path']);progress('inspect',1,1)
            write_json(directory/'inventory.json',inventory)
            mixed=render_mix(inventory,directory/'mix',progress,cancelled)
            analysis=analyze(Path(mixed['path']),directory/'analysis',job['params'],progress,cancelled)
        else:
            parent=self.store.get(job['parent'])
            inventory=cards.read(parent['inventory_path']);assert_sources_current(inventory)
            analysis=cards.read(parent['analysis_path'])
            write_json(directory/'inventory.json',inventory);write_json(directory/'analysis.json',analysis)
        report=render(analysis,directory/'render',job['params'],job['excluded'],progress,cancelled)
        analysis_path=directory/'analysis'/'analysis.json' if operation=='analyze' else directory/'analysis.json'
        if cancelled():raise InterruptedError('Job cancelled')
        stage=transaction.stage(inventory,report,directory/'stage')
        return dict(state='ready',report_path=str(directory/'render/report.json'),analysis_path=str(analysis_path),
                    inventory_path=str(directory/'inventory.json'),stage_path=str(stage),progress=dict(stage='ready',done=1,total=1))

    def close(self):
        if self.closed:return
        self.closed=True;self.stop.set()
        for event in self.cancel_events.values():event.set()
        self.worker.join(timeout=15)
        if self.worker.is_alive():raise RuntimeError('Worker is still completing a safe transaction; wait before restart')
        self.store.close()
