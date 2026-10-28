"""Discover local CapCut projects from stores, indexes and OS search metadata.

Cataloguing never requires opening or validating an editable timeline.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from .legacy import cards


def read_object(path):
    try:
        if path.stat().st_size>20_000_000:return {}
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        return data if isinstance(data,dict) else {}
    except (ValueError,OSError):return {}


def user_data_dirs():
    home=Path.home()
    locations=[home/'Movies/CapCut/User Data',home/'Library/Application Support/CapCut/User Data']
    for key in ('LOCALAPPDATA','APPDATA'):
        if os.environ.get(key):locations.append(Path(os.environ[key])/'CapCut/User Data')
    return locations


def directories(roots=None):
    """Known stores + CapCut's custom path hints + mounted indexed drafts."""
    explicit=roots is not None
    stores=list(roots) if explicit else cards.project_roots()
    candidates=set();seen=set();errors=[]
    if not explicit:
        for base in user_data_dirs():
            projects=base/'Projects'
            if projects.is_dir():
                stores.extend(p for p in projects.iterdir() if p.is_dir() and (p.name=='com.lveditor.draft' or p.name.startswith('com.lveditor.cloud.draft')))
            config=base/'Config'
            if config.is_dir():
                for p in config.iterdir():
                    if not p.is_file() or not any(k in p.name.casefold() for k in ('globalsetting','common','draft','path','setting')):continue
                    try:
                        if p.stat().st_size<=1_000_000:
                            for line in p.read_text(encoding='utf-8-sig',errors='replace').splitlines():
                                key,separator,value=line.partition('=');key=key.casefold()
                                if separator and any(k in key for k in ('draft','project')) and any(k in key for k in ('path','folder','dir')):
                                    value=value.strip().strip('"');path=Path(value).expanduser()
                                    if path.is_absolute() and path.is_dir():stores.append(path)
                    except OSError:pass
                    obj=read_object(p)
                    def visit(value):
                        if isinstance(value,dict):
                            for key,item in value.items():
                                if isinstance(item,str) and any(k in key.casefold() for k in ('draft','project')) and any(k in key.casefold() for k in ('path','folder','dir')):
                                    path=Path(item).expanduser()
                                    if path.is_absolute() and path.is_dir():stores.append(path)
                                elif isinstance(item,(dict,list)):visit(item)
                        elif isinstance(value,list):
                            for item in value:visit(item)
                    visit(obj)
        if sys.platform=='darwin':
            try:
                result=subprocess.run(['mdfind','-0',"kMDItemFSName == 'draft_meta_info.json' || kMDItemFSName == 'root_meta_info.json' || kMDItemFSName == 'draft_info.json'"],capture_output=True,timeout=8)
                for value in result.stdout.decode(errors='replace').split('\0'):
                    if not value:continue
                    path=Path(value)
                    if any(part in {'.Trash','.capcut-backups','.work','card-stages','backups','Timelines','Resources','Cache','Presets'} for part in path.parts):continue
                    if path.name=='root_meta_info.json':stores.append(path.parent)
                    else:candidates.add(path.parent)
            except (OSError,subprocess.TimeoutExpired):errors.append('OS project search unavailable; using CapCut stores and saved paths')
    while stores:
        root=Path(stores.pop()).expanduser()
        try:root=root.resolve(strict=True)
        except OSError:continue
        if root in seen or not root.is_dir():continue
        seen.add(root)
        if any((root/name).is_file() for name in ('draft_info.json','draft_content.json','draft_meta_info.json')):
            candidates.add(root);continue
        index=read_object(root/'root_meta_info.json')
        for row in index.get('all_draft_store',[]):
            if not isinstance(row,dict) or row.get('tm_draft_removed',0):continue
            value=row.get('draft_fold_path')
            if value and Path(value).is_absolute():candidates.add(Path(value))
            value=row.get('draft_root_path')
            if value and Path(value).is_absolute() and Path(value)!=root:stores.append(Path(value))
        try:
            for path in root.iterdir():
                if path.is_dir() and not path.is_symlink() and any((path/name).is_file() for name in ('draft_info.json','draft_content.json','draft_meta_info.json')):
                    candidates.add(path)
        except OSError:errors.append('Cannot read project store: '+str(root))
    results=[]
    for path in sorted(candidates):
        try:
            path=path.resolve(strict=True)
            if path.is_dir() and any((path/name).is_file() for name in ('draft_info.json','draft_content.json','draft_meta_info.json')):results.append(path)
        except OSError:continue
    return sorted(set(results)),errors


def metadata(path):
    path=Path(path).resolve();meta=read_object(path/'draft_meta_info.json')
    duration=meta.get('tm_duration',0)
    try:duration=max(0,float(duration)/1e6)
    except (ValueError,TypeError):duration=0
    return dict(name=meta.get('draft_name') or path.name,path=str(path),duration=duration,discovered=True)
