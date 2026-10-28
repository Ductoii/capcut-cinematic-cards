"""Atomic on-disk job records and a single service owner."""
import datetime
import json
import os
import re
import threading
from pathlib import Path

from .legacy import cards


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


class JobStore:
    def __init__(self,root):
        self.root=Path(root).expanduser().resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.owner=self.root/'service.lock'
        try:
            with self.owner.open('x') as f:f.write(str(os.getpid()))
        except FileExistsError:
            try:pid=int(self.owner.read_text());os.kill(pid,0)
            except ProcessLookupError:
                self.owner.unlink()
                with self.owner.open('x') as f:f.write(str(os.getpid()))
            else:raise ValueError('Harness is already running for this state folder')
        (self.root/'jobs').mkdir(exist_ok=True)
        self.records={}
        for path in (self.root/'jobs').glob('*/job.json'):
            if path.is_symlink() or path.parent.is_symlink():continue
            item=cards.read(path);ident=item.get('id','')
            if not re.fullmatch(r'[a-f0-9]{2,40}',ident) or path.parent.name!=ident:continue
            self.records[ident]=item
            if item['state'] in ('queued','running','applying','restoring'):
                item.update(state='interrupted',error='Harness stopped before the job completed. Retry as a new job.',updated_at=now())
                self.save(item)

    def write(self,path,value):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        cards.atomic(path,cards.encoded(value))

    def save(self,item):
        with self.lock:
            self.records[item['id']]=item
            self.write(self.root/'jobs'/item['id']/'job.json',item)

    def get(self,ident):
        with self.lock:
            if not isinstance(ident,str) or ident not in self.records:raise ValueError('Unknown job')
            return json.loads(json.dumps(self.records[ident]))

    def update(self,ident,**fields):
        with self.lock:
            item=self.get(ident);item.update(fields,updated_at=now());self.save(item);return item

    def close(self):
        if self.owner.exists() and self.owner.read_text()==str(os.getpid()):self.owner.unlink()
