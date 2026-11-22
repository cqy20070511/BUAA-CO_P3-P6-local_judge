"""打包前检查完整性，产出完整评测包和按题分类的测试点 code 合集。"""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))
    validation=json.loads((ROOT/'验证记录.json').read_text(encoding='utf-8'))
    assert len(manifest)==39 and all(len(v['cases'])==24 for v in manifest.values())
    assert len(validation['reference'])==48
    assert all(r['passed']==24 and r['total']==24 for r in validation['reference'])
    assert validation['integrity']['errors']==[]
    assert {'CE','TLE','WA'} <= set(validation['status_checks'])
    for spec in manifest.values():
        checks=[]
        for case in spec['cases']:
            path=ROOT/spec['path']/case['id']/'code.txt'
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==case['sha256'];checks.append(digest)
        assert len(set(checks))==24
    output=ROOT.parent
    full=output/'P6题目册与仿真评测合集.zip'
    with zipfile.ZipFile(full,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(ROOT.rglob('*')):
            relative=path.relative_to(ROOT)
            if not path.is_file() or any(part in ('runs','submissions','__pycache__') for part in relative.parts):continue
            if path.suffix=='.pyc':continue
            z.write(path,(Path(ROOT.name)/relative).as_posix())
    code=output/'P6测试点code合集.zip'
    with zipfile.ZipFile(code,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted((ROOT/'tests').rglob('*')):
            if path.is_file():z.write(path,path.relative_to(ROOT/'tests').as_posix())
        z.write(ROOT/'cases.json','cases.json')
        z.writestr('使用说明.txt','39 题，每题 24 个独立复位测试点，共 936 点。按往年题/Qxx、模拟题/Mxx 分类。\n'
                   '每点 code.txt 为工作区练习编码，code_original.txt 为已核实原平台编码（只在 Q11-Q19 提供）。\n'
                   'expected.log 为期望写入日志；program.lst 为带 PC 的指令清单；case.json 为周期、关注 PC、完成标记和 SHA-256。\n'
                   '机器码从 0x3000 起，每行一个字，填满 4096 个字。每点重新复位，DM 清零。\n'
                   '自动提交和逐点 AC/WA/TLE/CE/RE 评测入口在《P6题目册与仿真评测合集.zip》中。\n')
    for path in (full,code):
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            count=sum(n.endswith('/code.txt') for n in z.namelist())
            originals=sum(n.endswith('/code_original.txt') for n in z.namelist())
            assert count==936 and originals==216,(count,originals)
        print(path.name,path.stat().st_size,'bytes; 936 + 216 codes; CRC OK',flush=True)


if __name__=='__main__':main()
