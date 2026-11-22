"""本机 HTTP 集成检查：网页、目录/ZIP/多文件提交、实时结果和错误状态。"""
import base64
import json
from pathlib import Path
import sys
import time
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from judge import ROOT
BASE='http://127.0.0.1:8766'


def get(path):
    with urlopen(BASE+path,timeout=10) as response:return response.read()


def job(request):
    r=Request(BASE+'/api/jobs',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urlopen(r,timeout=15) as response:key=json.loads(response.read())['id']
    counts=[]
    for _ in range(500):
        result=json.loads(get('/api/jobs/'+key));counts.append(len(result['results']))
        if result['state'] in ('done','error'):break
        time.sleep(.1)
    assert result['state']=='done',result
    assert len(result['results'])==24,result
    return dict(request={k:v for k,v in request.items() if k!='files'},id=key,summary=result['summary'],
                intermediate_updates=sorted(set(n for n in counts if 0<n<24)))


def main():
    assert 'P6'.encode() in get('/')
    catalog=json.loads(get('/api/problems'));assert len(catalog)==39
    code=get('/api/code?problem=Q11&case=05&encoding=original').decode()
    assert len(code.splitlines())==4096 and '0000003c' in code
    reports=[]
    # 实际用户 ZIP，默认后端。
    source=Path('C:/Users/陈清扬/Desktop/SHL1.zip')
    if source.exists():
        r=job(dict(problem='Q11',encoding='original',files=[dict(name='SHL1.zip',data=base64.b64encode(source.read_bytes()).decode())]))
        assert r['summary']['passed']==24,r
        assert r['intermediate_updates'],r
        reports.append(r);print('ZIP / realtime: 24 AC',flush=True)
    r=job(dict(problem='Q14',encoding='practice',source_path='C:/Users/Public/Documents/ISE_projects/Q14'))
    assert r['summary']['passed']==24,r;reports.append(r);print('directory: 24 AC',flush=True)
    # 文件名中含目录时，上传仍能正确处理；故意语法错误必须逐点给出 CE。
    r=job(dict(problem='M01',encoding='practice',files=[dict(name='mips.v',data=base64.b64encode(b'module mips (BROKEN').decode())]))
    assert {x['status'] for x in r['summary']['results']}=={'CE'},r
    reports.append(r);print('broken upload: 24 CE',flush=True)
    multi=Path('C:/Users/Public/Documents/ISE_projects/Q15_1')
    if multi.is_dir():
        files=[dict(name=p.name,data=base64.b64encode(p.read_bytes()).decode()) for p in multi.iterdir()
               if p.is_file() and p.suffix.lower() in ('.v','.vh')]
        r=job(dict(problem='Q15',encoding='practice',files=files))
        assert r['summary']['passed']==24,r
        reports.append(r);print('multiple .v files: 24 AC',flush=True)
    (ROOT/'网页验证记录.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
