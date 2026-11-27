"""仅在本机监听的 P3 / P4 / P5 / P6 评测网页。Python 标准库，无需联网。"""
import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
import uuid
from urllib.parse import urlsplit,parse_qs,unquote,quote
from judge import ROOT,judge as p6_judge

P3ROOT=ROOT/'p3'
_p3_spec=importlib.util.spec_from_file_location('p3_judge',P3ROOT/'judge.py')
p3_judge=importlib.util.module_from_spec(_p3_spec);_p3_spec.loader.exec_module(p3_judge)
P5ROOT=ROOT/'p5'
_p5_spec=importlib.util.spec_from_file_location('p5_judge',P5ROOT/'judge.py')
p5_judge=importlib.util.module_from_spec(_p5_spec);_p5_spec.loader.exec_module(p5_judge)
P4ROOT=ROOT/'p4'
_p4_spec=importlib.util.spec_from_file_location('p4_judge',P4ROOT/'judge.py')
p4_judge=importlib.util.module_from_spec(_p4_spec);_p4_spec.loader.exec_module(p4_judge)
CATALOG=None

JOBS={}
LOCK=threading.RLock()
WORKER=threading.Lock()
SUBMISSIONS=ROOT/'submissions'
ACCESS_CODE=os.environ.get('ACCESS_CODE','').strip()
ALLOW_SOURCE_PATH=os.environ.get('ALLOW_SOURCE_PATH','1').strip().lower() not in ('0','false','no')
# 网页静态资源只允许这三项，避免把 runs/、tests/ 等目录暴露出去。
STATIC={'/assets/styles.css':('styles.css','text/css; charset=utf-8'),
        '/assets/app.js':('app.js','text/javascript; charset=utf-8'),
        '/assets/favicon.svg':('favicon.svg','image/svg+xml')}


def manifest():
    """把 P3、P4、P5、P6 题面合并，键形如 P3-E05 / P4-Q01 / P5-Q01 / P6-Q09。"""
    global CATALOG
    if CATALOG is None:
        merged={}
        for key,spec in json.loads((P3ROOT/'cases.json').read_text(encoding='utf-8')).items():
            merged['P3-'+key]={**spec,'stage':'P3','key':'P3-'+key}
        for key,spec in json.loads((P4ROOT/'cases.json').read_text(encoding='utf-8')).items():
            merged['P4-'+key]={**spec,'stage':'P4','key':'P4-'+key}
        for key,spec in json.loads((ROOT/'cases.json').read_text(encoding='utf-8')).items():
            merged['P6-'+key]={**spec,'stage':'P6','key':'P6-'+key}
        for key,spec in json.loads((P5ROOT/'cases.json').read_text(encoding='utf-8')).items():
            merged['P5-'+key]={**spec,'stage':'P5','key':'P5-'+key}
        CATALOG=merged
    return CATALOG


def normalize(key):
    key=str(key or '').upper()
    return key if '-' in key else 'P6-'+key


def snapshot(job):return {k:v for k,v in job.items() if not k.startswith('_')}


def save_meta(job):
    """把提交元数据写到 submissions/<id>/meta.json，服务重启后仍能在课下提交页看到。"""
    try:
        folder=SUBMISSIONS/job['id'];folder.mkdir(parents=True,exist_ok=True)
        summary=job.get('summary') or {}
        results=[{k:r.get(k) for k in ('id','label','title','status','message','cycles','budget') if k in r}
                 for r in (summary.get('results') or [])]
        data={'id':job.get('id'),'problem':job.get('problem'),'stage':job.get('stage'),
              'encoding':job.get('encoding'),'state':job.get('state'),'message':job.get('message'),
              'created':job.get('created'),'files':job.get('files_meta',[]),
              'source_path':job.get('source_path')}
        if summary:
            data['summary']={k:summary.get(k) for k in ('passed','total','seconds','record')}
            data['results']=results
        (folder/'meta.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except OSError:
        pass


def run_job(job,source):
    with WORKER:
        with LOCK:job['state']='running';job['message']='正在编译 RTL'
        def update(item):
            with LOCK:
                job['results'].append(item);job['message']=('正在评测：测试点 ' if job['stage']=='P3' else '正在仿真：测试点 ')+item['id']
        try:
            if job['stage']=='P3':
                result=p3_judge.judge(job['raw'],source,on_result=update)
                with LOCK:job['results']=result['results']
            elif job['stage']=='P4':
                result=p4_judge.judge(job['raw'],source,job['encoding'],on_result=update)
            elif job['stage']=='P5':
                result=p5_judge.judge(job['raw'],source,job['encoding'],on_result=update)
            else:
                result=p6_judge(job['raw'],source,job['encoding'],on_result=update)
            with LOCK:job.update(state='done',message='评测完成',summary=result)
        except Exception as e:
            with LOCK:job.update(state='error',message=str(e))
        save_meta(job)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def allowed(self):
        if not ACCESS_CODE:return True
        if self.headers.get('X-Access-Code','')==ACCESS_CODE:return True
        cookie=self.headers.get('Cookie','')
        for part in cookie.split(';'):
            name,_,value=part.strip().partition('=')
            if name=='judge_code' and unquote(value)==ACCESS_CODE:return True
        return False
    def send(self,status,body,content_type='application/json; charset=utf-8',headers=None):
        if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        for name,value in (headers or {}).items():self.send_header(name,value)
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path.startswith('/api/') and not self.allowed():return self.send(401,{'error':'需要访问码'})
        if path=='/':return self.send(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
        if path in STATIC:
            name,kind=STATIC[path]
            return self.send(200,(ROOT/'assets'/name).read_bytes(),kind)
        if path=='/api/problems':return self.send(200,manifest())
        if path=='/api/submissions':
            items=[]
            for meta in sorted(SUBMISSIONS.glob('*/meta.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:200]:
                try:items.append(json.loads(meta.read_text(encoding='utf-8')))
                except (OSError,ValueError):pass
            return self.send(200,items)
        if path.startswith('/api/submissions/') and '/file/' in path:
            rest=path[len('/api/submissions/'):]
            job_id,_,name=rest.partition('/file/')
            if not re.fullmatch(r'[a-f0-9]{32}',job_id):return self.send(404,{'error':'记录不存在'})
            name=unquote(name)
            relative=Path(name)
            if not name or relative.name=='meta.json' or relative.is_absolute() or '..' in relative.parts or ':' in name:
                return self.send(400,{'error':'文件名非法'})
            base=(SUBMISSIONS/job_id).resolve();target=(base/relative).resolve()
            if base!=target and base not in target.parents:return self.send(400,{'error':'文件名非法'})
            if not target.is_file():return self.send(404,{'error':'文件不存在'})
            disposition=f"attachment; filename*=UTF-8''{quote(relative.name)}"
            return self.send(200,target.read_bytes(),'application/octet-stream',{'Content-Disposition':disposition})
        if path.startswith('/api/jobs/'):
            key=path.rsplit('/',1)[-1]
            with LOCK:item=snapshot(JOBS[key]) if key in JOBS else None
            return self.send(200 if item else 404,item or {'error':'记录不存在'})
        if path=='/api/code':
            query=parse_qs(urlsplit(self.path).query)
            spec=manifest().get(normalize(query.get('problem',[''])[0]));case=query.get('case',[''])[0]
            if not spec or case not in {c['id'] for c in spec['cases']}:return self.send(404,{'error':'测试点不存在'})
            original=query.get('encoding',['practice'])[0]=='original'
            if original and not spec['original']:return self.send(400,{'error':'本题没有原平台编码'})
            if spec['stage']=='P3':return self.send(404,{'error':'P3 不提供测试点机器码'})
            base=ROOT/'p4' if spec['stage']=='P4' else ROOT/'p5' if spec['stage']=='P5' else ROOT
            code=base/spec['path']/case/('code_original.txt' if original else 'code.txt')
            return self.send(200,code.read_bytes(),'text/plain; charset=utf-8')
        return self.send(404,{'error':'地址不存在'})
    def do_POST(self):
        # 阻止其他网页跨站向本机服务发起有副作用的请求。
        origin=self.headers.get('Origin')
        proto=self.headers.get('X-Forwarded-Proto','http')
        if origin and origin!=(f'{proto}://'+self.headers.get('Host','')):return self.send(403,{'error':'仅接受本站页面的请求'})
        if not self.allowed():return self.send(401,{'error':'需要访问码'})
        if urlsplit(self.path).path!='/api/jobs':return self.send(404,{'error':'地址不存在'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=30*1024*1024:raise ValueError('提交大小须在 30MB 以内')
            request=json.loads(self.rfile.read(length))
            key=normalize(request.get('problem',''))
            specs=manifest()
            if key not in specs:raise ValueError('题号不存在')
            spec=specs[key]
            encoding=request.get('encoding','practice')
            if encoding not in ('practice','original'):raise ValueError('编码选项错误')
            if encoding=='original' and not spec['original']:raise ValueError('没有已核实的原编码')
            job_id=uuid.uuid4().hex
            job_dir=ROOT/'submissions'/job_id;job_dir.mkdir(parents=True)
            uploaded=[]
            if request.get('source_path') and not ALLOW_SOURCE_PATH:raise ValueError('公网部署不允许填写本机路径，请上传文件')
            if spec['stage']=='P3':
                if request.get('source_path'):
                    source=Path(request['source_path']).expanduser().resolve()
                    if not source.is_file() or source.suffix.lower()!='.circ':raise ValueError('P3 需要 .circ 文件')
                else:
                    upload=request.get('files',[])
                    if len(upload)!=1:raise ValueError('P3 只提交一个 .circ 文件')
                    item=upload[0];name=str(item['name']).replace('\\','/');relative=Path(name)
                    if relative.is_absolute() or '..' in relative.parts or ':' in name:raise ValueError('文件名非法')
                    if relative.suffix.lower()!='.circ':raise ValueError('P3 只接收 .circ 文件')
                    content=base64.b64decode(item['data'],validate=True)
                    if len(content)>20*1024*1024:raise ValueError('电路文件超过 20MB')
                    source=job_dir/relative.name;source.write_bytes(content)
                    uploaded.append({'name':relative.name,'size':len(content)})
            elif request.get('source_path'):
                source=Path(request['source_path']).expanduser().resolve()
                if not source.exists():raise ValueError('源码路径不存在')
            else:
                upload=request.get('files',[])
                if not 1<=len(upload)<=100:raise ValueError('选择一个 ZIP 或最多 100 个 .v/.vh 文件')
                total=0;seen=set()
                for item in upload:
                    name=str(item['name']).replace('\\','/')
                    relative=Path(name)
                    if relative.is_absolute() or '..' in relative.parts or ':' in name:raise ValueError('文件名非法')
                    if relative.suffix.lower() not in ('.zip','.v','.vh'):raise ValueError('只接收 ZIP、.v、.vh')
                    if name.lower() in seen:raise ValueError('同名文件重复')
                    seen.add(name.lower());content=base64.b64decode(item['data'],validate=True);total+=len(content)
                    if total>20*1024*1024:raise ValueError('源码总大小超过 20MB')
                    target=job_dir/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
                    uploaded.append({'name':relative.as_posix(),'size':len(content)})
                zips=list(job_dir.rglob('*.zip'))
                if zips and (len(zips)!=1 or len(upload)!=1):raise ValueError('ZIP 必须单独上传')
                source=zips[0] if zips else job_dir
            job=dict(id=job_id,problem=key,stage=spec['stage'],raw=spec['id'],encoding=encoding,state='queued',message='等待评测',results=[],created=time.time(),files_meta=uploaded,source_path=str(source) if request.get('source_path') else None)
            with LOCK:JOBS[job_id]=job
            save_meta(job)
            threading.Thread(target=run_job,args=(job,source),daemon=True).start()
            return self.send(202,{'id':job_id})
        except (ValueError,KeyError,TypeError,OSError) as e:return self.send(400,{'error':str(e)})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default=os.environ.get('HOST','127.0.0.1'))
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8766')))
    args=parser.parse_args()
    with socket.socket() as probe:
        probe.settimeout(.4)
        if probe.connect_ex(('127.0.0.1',args.port))==0:
            print(f'端口 {args.port} 已有评测机在运行，请先关闭原窗口，或改用 --port 其他端口。',flush=True)
            return
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'P3 / P4 / P5 / P6 评测器已启动：http://{args.host}:{args.port}  （按 Ctrl+C 退出）',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
