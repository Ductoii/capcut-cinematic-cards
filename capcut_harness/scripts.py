"""Project-bound immutable plain-text screenplays; never written into a draft."""
import hashlib
from pathlib import Path
import re

from .jobs import now
from .legacy import cards

MAX_BYTES=512_000


class Scripts:
    def __init__(self,service):self.service=service;self.root=service.root/'scripts'

    def summary(self,project_id):
        self.service._project(project_id)
        path=self.root/project_id/'latest.json'
        return cards.read(path) if path.exists() else None

    def save(self,project_id,text,file_name='Kịch bản.txt'):
        self.service._project(project_id)
        if not isinstance(text,str) or not text.strip():raise ValueError('Kịch bản không được để trống')
        if '\x00' in text:raise ValueError('Chỉ nhận kịch bản dạng text')
        raw=text.encode('utf-8')
        if len(raw)>MAX_BYTES:raise ValueError('Kịch bản tối đa 512 KB text UTF-8')
        signature=hashlib.sha256(raw).hexdigest();directory=self.root/project_id;directory.mkdir(parents=True,exist_ok=True)
        path=directory/(signature+'.txt')
        if not path.exists():cards.atomic(path,raw)
        file_name=Path(str(file_name)).name[:160]
        summary=dict(project_id=project_id,sha256=signature,characters=len(text),bytes=len(raw),file_name=file_name,saved_at=now(),
                     data_path=f'/api/projects/{project_id}/scripts/{signature}')
        self.service.store.write(directory/'latest.json',summary)
        return summary

    def read(self,project_id,signature):
        self.service._project(project_id)
        if not isinstance(signature,str) or not re.fullmatch(r'[a-f0-9]{64}',signature):raise ValueError('Invalid script revision')
        path=self.root/project_id/(signature+'.txt')
        if path.is_symlink() or not path.is_file():raise ValueError('Script revision not found')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=signature:raise ValueError('Saved script changed')
        return dict(project_id=project_id,sha256=signature,text=raw.decode('utf-8'),characters=len(raw.decode('utf-8')))
