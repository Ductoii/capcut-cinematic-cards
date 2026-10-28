"""Durable UI requests. The MCP host, not this service, routes chat messages."""
import copy
import re
import threading
import uuid

from .jobs import now
from .legacy import cards

TERMINAL={'complete','blocked','failed','cancelled'}


def caller_thread(meta):
    meta=meta or {}
    for key in ('openai/threadId','openai/thread_id','codexThreadId','threadId','thread_id'):
        value=meta.get(key)
        if isinstance(value,str) and value:return value
    turn=meta.get('x-codex-turn-metadata',{})
    if isinstance(turn,str):
        import json
        try:turn=json.loads(turn)
        except ValueError:turn={}
    return turn.get('thread_id') if isinstance(turn,dict) else None


class Workspace:
    def __init__(self,service):
        self.service=service;self.path=service.root/'workspaces.json';self.lock=threading.RLock()
        self.data=cards.read(self.path) if self.path.exists() else dict(connections={},requests={})

    def save(self):self.service.store.write(self.path,self.data)

    def open(self,thread_id=None):
        with self.lock:
            connection=dict(id=uuid.uuid4().hex,thread_id=thread_id,created_at=now())
            self.data['connections'][connection['id']]=connection;self.save()
            return copy.deepcopy(connection)

    def connection(self,ident,thread_id=None):
        connection=self.data['connections'].get(ident)
        if connection is None:raise ValueError('Unknown workspace')
        if thread_id and connection.get('thread_id') and thread_id!=connection['thread_id']:
            raise ValueError('Workspace belongs to another chat')
        return connection

    def list(self,connection_id,thread_id=None):
        with self.lock:
            self.connection(connection_id,thread_id)
            return copy.deepcopy(sorted([r for r in self.data['requests'].values() if r['connection_id']==connection_id],key=lambda r:r['created_at'])[-50:])

    def submit(self,connection_id,ident,text,project_id=None,context=None,thread_id=None):
        if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9-]{32,36}',ident):raise ValueError('Request UUID required')
        if not isinstance(text,str) or not 0<len(text.strip())<=12000:raise ValueError('Request must contain 1–12000 characters')
        if context is not None and not isinstance(context,dict):raise ValueError('Request context must be an object')
        if project_id:self.service._project(project_id)
        with self.lock:
            self.connection(connection_id,thread_id)
            context=copy.deepcopy(context or {})
            if project_id:
                summary=self.service.scripts.summary(project_id)
                signature=context.get('script_sha256') or (summary or {}).get('sha256')
                if signature:
                    script=self.service.scripts.read(project_id,signature)
                    context['script']=dict(sha256=signature,characters=script['characters'],data_path=f'/api/projects/{project_id}/scripts/{signature}')
            body=dict(connection_id=connection_id,text=text,project_id=project_id,context=context)
            if ident in self.data['requests']:
                saved=self.data['requests'][ident]
                if saved['input_hash']!=cards.object_hash(body):raise ValueError('Request ID reused with different input')
                return copy.deepcopy(saved)
            item=dict(id=ident,**body,input_hash=cards.object_hash(body),state='saved',created_at=now(),updated_at=now(),events=[])
            self.data['requests'][ident]=item;self.save();return copy.deepcopy(item)

    def get(self,ident,thread_id=None):
        with self.lock:
            item=self.data['requests'].get(ident)
            if item is None:raise ValueError('Unknown UI request')
            self.connection(item['connection_id'],thread_id);return copy.deepcopy(item)

    def update(self,ident,state,text='',job_id=None,stage_id=None,thread_id=None,from_ui=False):
        allowed={'saved','sent','delivery_uncertain','cancelled'} if from_ui else {'acknowledged','working',*TERMINAL}
        if state not in allowed or not isinstance(text,str) or len(text)>12000:raise ValueError('Invalid request event')
        with self.lock:
            item=self.get(ident,thread_id)
            if item['state'] in TERMINAL:return item
            if from_ui and item['state'] in ('acknowledged','working'):return item
            if job_id:self.service.job(job_id)
            item.update(state=state,updated_at=now())
            item['sequence']=item.get('sequence',0)+1
            event=dict(seq=item['sequence'],state=state,text=text,at=now())
            if job_id:event['job_id']=job_id
            if stage_id:event['stage_id']=stage_id
            item['events'].append(event);item['events']=item['events'][-200:]
            self.data['requests'][ident]=item;self.save();return copy.deepcopy(item)
