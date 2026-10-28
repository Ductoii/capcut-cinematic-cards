import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from capcut_harness.server import create_server
from capcut_harness.service import Service


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.service=Service(self.root/'state',[]);self.server=create_server(self.service,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_address[1];self.origin=f'http://127.0.0.1:{self.port}'
        self.addCleanup(self.finish)
        status,_,data=self.request('GET','/api/bootstrap');self.assertEqual(status,200)
        self.token=json.loads(data)['token']

    def finish(self):
        self.server.shutdown();self.server.server_close();self.service.close();self.thread.join(2)

    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        connection.request(method,path,body=body,headers=headers or {})
        response=connection.getresponse();data=response.read();result=(response.status,dict(response.getheaders()),data);connection.close();return result

    def auth(self):return {'X-Harness-Token':self.token,'Origin':self.origin,'Content-Type':'application/json'}

    def test_token_origin_and_host_are_required_for_mutation(self):
        body=json.dumps(dict(text='cân âm thoại unknown'))
        self.assertEqual(self.request('POST','/api/command',body)[0],403)
        headers=self.auth();headers['Origin']='https://evil.example'
        self.assertEqual(self.request('POST','/api/command',body,headers)[0],403)
        headers=self.auth();headers['Host']='evil.example'
        self.assertEqual(self.request('POST','/api/command',body,headers)[0],403)
        self.assertEqual(self.request('POST','/api/command',body,self.auth())[0],400)
        self.assertEqual(self.request('GET','/api/jobs')[0],403)
        self.assertEqual(self.request('GET','/api/jobs',headers=self.auth())[0],200)

    def test_bad_json_size_unknown_actions_and_traversal(self):
        self.assertEqual(self.request('POST','/api/action','{broken',self.auth())[0],400)
        # Reject the oversized declared body before accepting/allocating it.
        self.assertEqual(self.request('POST','/api/action','',{**self.auth(),'Content-Length':'1100000'})[0],413)
        self.assertEqual(self.request('POST','/api/action','{"action":"shell.run"}',self.auth())[0],400)
        self.assertEqual(self.request('GET','/../../LICENSE',headers=self.auth())[0],404)
        self.assertEqual(self.request('GET','/media/../../LICENSE',headers=self.auth())[0],404)
        self.assertEqual(self.request('DELETE','/api/jobs',headers=self.auth())[0],405)

    def test_media_is_job_owned_allowlisted_and_range_seekable(self):
        ident='aabbcc';directory=self.service.root/'jobs'/ident;directory.mkdir(parents=True)
        media=directory/'before.wav';media.write_bytes(b'0123456789')
        report=directory/'report.json';report.write_text(json.dumps(dict(before_preview=str(media))))
        self.service.store.save(dict(id=ident,state='ready',report_path=str(report),created_at='2026-10-28'))
        status,headers,data=self.request('GET',f'/media/{ident}/before.wav',headers={**self.auth(),'Range':'bytes=2-5'})
        self.assertEqual(status,206);self.assertEqual(data,b'2345');self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertEqual(self.request('GET',f'/media/{ident}/report.json',headers=self.auth())[0],404)
        media.unlink();media.symlink_to(self.root/'private.txt');(self.root/'private.txt').write_text('secret')
        self.assertEqual(self.request('GET',f'/media/{ident}/before.wav',headers=self.auth())[0],404)


if __name__=='__main__':unittest.main()
