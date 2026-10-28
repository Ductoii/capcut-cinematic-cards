"""Finite, documented command vocabulary; text never becomes executable code."""
import re
import unicodedata

CAPABILITIES=[
    dict(id='dialogue',name='Cân âm thoại',actions=['dialogue.analyze','dialogue.render','dialogue.apply','dialogue.undo','dialogue.cancel','dialogue.retry']),
    dict(id='cards',name='Cinematic cards',actions=['cards.inspect','cards.stage','cards.apply','cards.verify','cards.restore']),
    dict(id='projects',name='Project',actions=['project.register','project.inspect']),
]


def folded(text):
    return ''.join(ch for ch in unicodedata.normalize('NFD',text.casefold().replace('đ','d')) if unicodedata.category(ch)!='Mn')


def parse_command(text,projects,project_id=None):
    if not isinstance(text,str) or not 0<len(text.strip())<=500:raise ValueError('Lệnh trống hoặc quá dài')
    normalized=folded(text.strip())
    for pattern,action in [(r'(?:thu lai|retry)\s+([a-z0-9-]+)','dialogue.retry'),(r'(?:ap dung|apply)\s+([a-z0-9-]+)','dialogue.apply'),(r'(?:hoan tac|undo)\s+([a-z0-9-]+)','dialogue.undo')]:
        m=re.fullmatch(pattern,normalized)
        if m:return dict(action=action,job_id=m.group(1))
    patterns=[(r'(?:can am(?: thoai)?|normalize(?: dialogue)?)\s*(.*)','dialogue.analyze'),
              (r'(?:phan tich|inspect)\s*(.*)','project.inspect')]
    for pattern,action in patterns:
        m=re.fullmatch(pattern,normalized)
        if m:
            name=m.group(1).strip().strip('"\'')
            matches=[p for p in projects if folded(p['name'])==name or p['id']==name] if name else [p for p in projects if p['id']==project_id]
            if len(matches)!=1:raise ValueError('Project thiếu hoặc trùng tên; chọn project rồi gửi lại lệnh')
            result=dict(action=action,project_id=matches[0]['id'])
            if action=='dialogue.analyze':result['params']={}
            return result
    raise ValueError('Lệnh chưa hỗ trợ. Dùng: phân tích <project>, cân âm thoại <project>, áp dụng <job>, hoàn tác <job>')
