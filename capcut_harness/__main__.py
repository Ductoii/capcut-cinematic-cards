"""Launch a local editing workspace or use the same registry from the CLI."""
import argparse
import json
import sys
import webbrowser
from pathlib import Path

from .service import Service
from .server import create_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,default=Path.home()/'.local/share/capcut-harness')
    parser.add_argument('--project-root',type=Path,action='append')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    sub=parser.add_subparsers(dest='command')
    view=sub.add_parser('inspect');view.add_argument('project')
    command=sub.add_parser('command');command.add_argument('text')
    args=parser.parse_args()
    service=Service(args.state_dir,args.project_root)
    try:
        if args.command=='inspect':
            project=service.register(Path(args.project));print(json.dumps(service.inspect(project['id']),ensure_ascii=False,indent=2));return
        if args.command=='command':
            print(json.dumps(service.command(args.text),ensure_ascii=False,indent=2));return
        server=create_server(service,args.port);url=f'http://127.0.0.1:{server.server_address[1]}/'
        service.store.write(service.root/'server.json',dict(url=url,pid=__import__('os').getpid()))
        print(json.dumps(dict(url=url,state_dir=str(service.root)),ensure_ascii=False),flush=True)
        if not args.no_browser:webbrowser.open(url)
        try:server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:service.close()


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
