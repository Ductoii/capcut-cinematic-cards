"""Launch the local workspace; CLI commands share its registry and wait for results."""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from .service import Service
from .server import create_server


def wait_result(ticket, get_job):
    if 'job_id' not in ticket:return ticket
    while True:
        job=get_job(ticket['job_id'])
        if job['state'] not in ('queued','running','applying','restoring'):
            return dict(ticket,state=job['state'],error=job.get('error'),report_path=job.get('report_path'))
        time.sleep(.2)


class Client:
    def __init__(self,url):
        if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}/',url):raise ValueError('Invalid local server URL')
        self.url=url.rstrip('/');self.token='';self.token=self.request('/api/bootstrap')['token']

    def request(self,path,data=None):
        request=urllib.request.Request(self.url+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,
            headers={'X-Harness-Token':self.token,'Origin':self.url,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(json.load(exc).get('error',str(exc))) from exc


def existing_client(root):
    owner=root/'service.lock';record=root/'server.json'
    if not owner.exists():return None
    try:pid=int(owner.read_text());os.kill(pid,0)
    except ProcessLookupError:return None
    if not record.is_file():raise ValueError('Harness owns this state folder but its HTTP endpoint is unavailable')
    info=json.loads(record.read_text())
    if info['pid']!=pid:raise ValueError('Server ownership changed; preserve state and restart the owning harness')
    return Client(info['url'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,default=Path.home()/'.local/share/capcut-harness')
    parser.add_argument('--project-root',type=Path,action='append')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    sub=parser.add_subparsers(dest='command')
    view=sub.add_parser('inspect');view.add_argument('project')
    command=sub.add_parser('command');command.add_argument('text')
    args=parser.parse_args();args.state_dir=args.state_dir.expanduser().resolve()
    client=existing_client(args.state_dir)
    if client:
        if args.command=='inspect':
            project=client.request('/api/action',dict(action='project.register',path=str(Path(args.project).expanduser().resolve())))
            result=client.request('/api/projects/'+project['id'])
        elif args.command=='command':result=wait_result(client.request('/api/command',dict(text=args.text)),lambda ident:client.request('/api/jobs/'+ident))
        else:
            if not args.no_browser:webbrowser.open(client.url)
            result=dict(url=client.url,state_dir=str(args.state_dir),already_running=True)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result.get('error') else 0
    service=Service(args.state_dir,args.project_root)
    try:
        if args.command=='inspect':
            project=service.register(Path(args.project));result=service.inspect(project['id'])
        elif args.command=='command':result=wait_result(service.command(args.text),service.job)
        else:
            server=create_server(service,args.port);url=f'http://127.0.0.1:{server.server_address[1]}/'
            service.store.write(service.root/'server.json',dict(url=url,pid=os.getpid()))
            print(json.dumps(dict(url=url,state_dir=str(service.root)),ensure_ascii=False),flush=True)
            if not args.no_browser:webbrowser.open(url)
            try:server.serve_forever(poll_interval=.2)
            except KeyboardInterrupt:pass
            finally:server.server_close()
            return 0
        print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result.get('error') else 0
    finally:service.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
