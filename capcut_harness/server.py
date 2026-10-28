"""Loopback-only UI API with explicit session/origin checks and owned media."""
import http.cookies
import json
import mimetypes
import re
import secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit

from .actions import CAPABILITIES
from . import __version__

WEB=Path(__file__).parent/'web'
STATIC={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/app.css':'app.css','/charts.js':'charts.js',
        '/fonts/InterVariable.woff2':'fonts/InterVariable.woff2'}
MAX_BODY=1024*1024


def create_server(service,port=0):
    token=secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version='CapCutHarness'
        def log_message(self,*args):pass

        def headers_common(self):
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

        def json_response(self,status,data,cookie=False):
            raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.headers_common();self.send_header('Content-Type','application/json; charset=utf-8')
            if cookie:self.send_header('Set-Cookie',f'harness_session={token}; HttpOnly; SameSite=Strict; Path=/')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

        def local(self):
            number=self.server.server_address[1]
            hosts={f'127.0.0.1:{number}',f'localhost:{number}'}
            return len(self.headers.get_all('Host') or [])==1 and self.headers.get('Host') in hosts and self.headers.get('Sec-Fetch-Site') not in ('cross-site',)

        def authenticated(self):
            given=self.headers.get('X-Harness-Token','')
            if not given:
                cookie=http.cookies.SimpleCookie()
                try:cookie.load(self.headers.get('Cookie',''));given=cookie['harness_session'].value if 'harness_session' in cookie else ''
                except http.cookies.CookieError:return False
            return secrets.compare_digest(given,token)

        def route(self):return unquote(urlsplit(self.path).path)

        def do_GET(self):
            if not self.local():return self.json_response(403,dict(error='Local Host/Origin required'))
            path=self.route()
            if path=='/api/bootstrap':
                return self.json_response(200,dict(token=token,version=__version__,capabilities=CAPABILITIES),cookie=True)
            if path.startswith(('/api/','/media/')) and not self.authenticated():return self.json_response(403,dict(error='Local session required'))
            try:
                if path=='/api/projects':return self.json_response(200,service.projects())
                if path=='/api/jobs':return self.json_response(200,service.jobs())
                m=re.fullmatch(r'/api/jobs/([a-f0-9]{2,40})',path)
                if m:return self.json_response(200,service.job(m.group(1)))
                m=re.fullmatch(r'/api/projects/([a-f0-9]{16})',path)
                if m:return self.json_response(200,service.inspect(m.group(1)))
                m=re.fullmatch(r'/media/([a-f0-9]{2,40})/(before\.wav|after\.wav|master\.wav)',path)
                if m:
                    job=service.job(m.group(1));report=job.get('report',{})
                    key={'before.wav':'before_preview','after.wav':'after_preview','master.wav':'master'}[m.group(2)]
                    value=report.get(key)
                    if not value:return self.json_response(404,dict(error='Preview not ready'))
                    target=Path(value);owned=service.root/'jobs'/m.group(1)
                    if target.is_symlink() or not target.resolve().is_relative_to(owned.resolve()):return self.json_response(404,dict(error='Unowned preview path'))
                    return self.file(target,'audio/wav',ranges=True)
                if path in STATIC:
                    return self.file(WEB/STATIC[path],mimetypes.guess_type(path if path!='/' else 'index.html')[0] or 'application/octet-stream')
                return self.json_response(404,dict(error='Not found'))
            except (ValueError,KeyError,OSError) as exc:return self.json_response(400,dict(error=str(exc)))

        def file(self,path,content_type,ranges=False):
            path=Path(path)
            if not path.is_file() or path.is_symlink():return self.json_response(404,dict(error='File not available'))
            size=path.stat().st_size;start=0;end=size-1;partial=False
            requested=self.headers.get('Range') if ranges else None
            if requested:
                m=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                if not m or (not m.group(1) and not m.group(2)):
                    return self.json_response(416,dict(error='Invalid byte range'))
                if not m.group(1):start=max(0,size-int(m.group(2)))
                else:start=int(m.group(1))
                if m.group(1) and m.group(2):end=min(end,int(m.group(2)))
                if start>end or start>=size:return self.json_response(416,dict(error='Range outside media'))
                partial=True
            self.send_response(206 if partial else 200);self.headers_common()
            self.send_header('Content-Type',content_type)
            if ranges:self.send_header('Accept-Ranges','bytes')
            if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.send_header('Content-Length',str(max(0,end-start+1)));self.end_headers()
            try:
                with path.open('rb') as f:
                    f.seek(start);remaining=end-start+1
                    while remaining>0:
                        chunk=f.read(min(256*1024,remaining))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):pass

        def do_POST(self):
            number=self.server.server_address[1]
            if not self.local() or not self.authenticated() or self.headers.get('Origin') not in (f'http://127.0.0.1:{number}',f'http://localhost:{number}') or not secrets.compare_digest(self.headers.get('X-Harness-Token',''),token):
                return self.json_response(403,dict(error='Local session and matching Origin required'))
            try:
                length=int(self.headers.get('Content-Length','-1'))
                if length<0 or self.headers.get('Transfer-Encoding'):return self.json_response(400,dict(error='Content-Length required'))
                if length>MAX_BODY:return self.json_response(413,dict(error='Request too large'))
                if self.headers.get_content_type()!='application/json':return self.json_response(400,dict(error='Use application/json'))
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('JSON object required')
                if self.route()=='/api/action':result=service.dispatch(data)
                elif self.route()=='/api/command':result=service.command(data.get('text'),data.get('project_id'))
                else:return self.json_response(404,dict(error='Not found'))
                return self.json_response(200,result)
            except (ValueError,KeyError,TypeError,OSError) as exc:return self.json_response(400,dict(error=str(exc)))

        def do_DELETE(self):return self.json_response(405,dict(error='Method not allowed'))
        do_PUT=do_DELETE
        do_PATCH=do_DELETE

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True;server.service=service;server.token=token
    return server
