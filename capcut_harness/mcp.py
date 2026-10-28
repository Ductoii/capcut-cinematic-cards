"""Local stdio MCP App. No second model, native socket access or cloud media."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from . import __version__
from .__main__ import existing_client
from .workspace import caller_thread

RESOURCE='ui://capcut-harness/workspace-v030.html'
WEB=Path(__file__).parent/'web'
STATE=Path(os.environ.get('CAPCUT_HARNESS_STATE',Path.home()/'.local/share/capcut-harness')).expanduser().resolve()


def backend():
    client=existing_client(STATE)
    if client:
        if client.request('/api/bootstrap').get('version')!=__version__:
            raise ValueError('A previous harness service is running. Run the managed installer to upgrade it without losing jobs.')
        return client
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'daemon.log').open('ab') as log:
        proc=subprocess.Popen([sys.executable,'-m','capcut_harness','--state-dir',str(STATE),'--no-browser'],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=Path(__file__).parent.parent)
    for _ in range(250):
        try:
            client=existing_client(STATE)
            if client:return client
        except (ValueError,OSError):pass
        if proc.poll() is not None:raise ValueError('Local workspace could not start; see daemon.log')
        time.sleep(.1)
    raise ValueError('Local workspace is still starting')


def schema(properties,required=()):return dict(type='object',properties=properties,required=list(required),additionalProperties=False)
S=dict(type='string');O=dict(type='object');B=dict(type='boolean')
TOOLS=[
    dict(name='capcut_open_workspace',description='Open the local CapCut Harness panel in this chat. Includes cinematic time/location/character cards and film dialogue leveling. Use when starting the capcut-harness skill.',
         inputSchema=schema({}),annotations=dict(readOnlyHint=True),
         _meta=dict(ui=dict(resourceUri=RESOURCE),**{'openai/ui':dict(entrypoints=[dict(type='thread')])})),
    dict(name='capcut_workspace_data',description='Read bounded local workspace/project/job data and saved UI requests.',
         inputSchema=schema(dict(connection_id=S,path=S),['connection_id','path']),annotations=dict(readOnlyHint=True)),
    dict(name='capcut_action',description='Execute one structured CapCut action. Analysis makes a listening master; Apply/Undo retain editor-closed and freshness guards. Card staging requires an evidence-based plan.',
         inputSchema=schema(dict(connection_id=S,action=O),['connection_id','action'])),
    dict(name='capcut_request_create',description='Save a freeform UI request before sending it to the current chat through the host UI message bridge.',
         inputSchema=schema(dict(connection_id=S,id=S,text=S,project_id=S,context=O),['connection_id','id','text'])),
    dict(name='capcut_request_get',description='Read the authoritative context and state for a UI request before working on it. A completed request must not be executed twice.',
         inputSchema=schema(dict(id=S),['id']),annotations=dict(readOnlyHint=True)),
    dict(name='capcut_request_update',description='Acknowledge a UI request, publish work progress, and return a complete/blocked/failed result to its panel. Link the job or card stage when available.',
         inputSchema=schema(dict(id=S,state=dict(type='string',enum=['acknowledged','working','complete','blocked','failed','cancelled','sent','delivery_uncertain']),text=S,job_id=S,stage_id=S,from_ui=B),['id','state'])),
]


def result(data,private=None):
    value=dict(content=[dict(type='text',text=json.dumps(data,ensure_ascii=False))],structuredContent=data if isinstance(data,dict) else dict(data=data))
    if private:value['_meta']=private
    return value


def component(origin):
    html=(WEB/'index.html').read_text()
    html=re.sub(r'<link rel="preload"[^>]*>','',html)
    html=html.replace('<link rel="stylesheet" href="/app.css">','<style>'+ (WEB/'app.css').read_text()+'</style>')
    html=re.sub(r'<script src="/[^\"]+" defer></script>','',html)
    font=base64.b64encode((WEB/'fonts/InterVariable.woff2').read_bytes()).decode()
    html=html.replace("url('/fonts/InterVariable.woff2')",f"url('data:font/woff2;base64,{font}')")
    scripts='\n'.join((WEB/name).read_text() for name in ['host.js','charts.js','app.js'])
    return html.replace('</body>','<script>window.CAPCUT_MCP=true;window.CAPCUT_MEDIA_ORIGIN='+json.dumps(origin)+';\n'+scripts+'</script></body>')


def handle(request):
    method=request.get('method');p=request.get('params',{})
    if method=='initialize':return dict(protocolVersion=p.get('protocolVersion','2024-11-05'),
        capabilities=dict(tools={},resources={}),serverInfo=dict(name='capcut-harness',version=__version__),
        instructions='Use capcut_open_workspace to start. UI follow-ups are user requests in this same chat. Retrieve request context, acknowledge, do the work, then publish progress/result with capcut_request_update. Do not use another model or treat text as a fixed command grammar.')
    if method=='ping':return {}
    if method=='tools/list':return dict(tools=TOOLS)
    if method=='resources/list':return dict(resources=[dict(uri=RESOURCE,name='CapCut Harness',mimeType='text/html;profile=mcp-app')])
    if method=='resources/read':
        if p.get('uri')!=RESOURCE:raise ValueError('Unknown UI resource')
        client=backend();origin=client.url
        return dict(contents=[dict(uri=RESOURCE,mimeType='text/html;profile=mcp-app',text=component(origin),
            _meta=dict(ui=dict(prefersBorder=False,csp=dict(connectDomains=[origin],resourceDomains=[origin]))))])
    if method=='tools/call':
        name=p.get('name');a=p.get('arguments') or {};thread=caller_thread(p.get('_meta'))
        if name not in {t['name'] for t in TOOLS}:raise ValueError('Unknown tool')
        client=backend()
        def call(op,**values):return client.request('/api/workspace',dict(operation=op,thread_id=thread,**values))
        if name=='capcut_open_workspace':
            connection=call('open');return result(dict(connection_id=connection['id'],chat_bridge='host-ui-message',
                note='UI messages are routed by the hosting chat. No other model/session is started.'),dict(media_origin=client.url))
        if name=='capcut_workspace_data':
            if a.get('path')=='/api/requests':data=call('requests',connection_id=a['connection_id'])
            else:data=call('data',connection_id=a['connection_id'],path=a['path'])
            private={}
            if isinstance(data,dict) and 'media_capability' in data:
                key=data.pop('media_capability');private=dict(media_origin=client.url,media_base=f'{client.url}/media-cap/{key}/{data["id"]}')
            return result(data,private)
        if name=='capcut_action':return result(call('action',**a))
        if name=='capcut_request_create':return result(call('submit',**a))
        if name=='capcut_request_get':return result(call('get',**a))
        if name=='capcut_request_update':return result(call('update',**a))
    raise ValueError('Unsupported MCP method')


def main():
    for line in sys.stdin:
        if len(line)>2*1024*1024:continue
        request={}
        try:
            request=json.loads(line)
            if 'id' not in request:continue
            value=handle(request);response=dict(jsonrpc='2.0',id=request['id'],result=value)
        except Exception as exc:
            response=dict(jsonrpc='2.0',id=request.get('id'),error=dict(code=-32603,message=str(exc)))
        print(json.dumps(response,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':main()
