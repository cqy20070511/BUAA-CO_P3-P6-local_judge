"""Compile an isolated CPU snapshot and compare its own write log and state."""
from pathlib import Path
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
EVENT = re.compile(r'@\s*([0-9a-fA-FxXzZ]+)\s*:\s*([$*])\s*([0-9a-fA-FxXzZ]+)\s*<=\s*([0-9a-fA-FxXzZ]+)')


def parse_log(text):
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        match = EVENT.search(line)
        if not match:
            if '@' in line and '<=' in line:
                raise ValueError(f'line {number}: malformed write event: {line}')
            continue
        pc, kind, location, value = match.groups()
        if any(char in (pc+location+value).lower() for char in 'xz'):
            raise ValueError(f'line {number}: X/Z in write event: {line}')
        target = int(location, 10 if kind == '$' else 16)
        event = (int(pc,16), kind, target, int(value,16))
        if not 0 <= event[0] <= 0xffffffff or not 0 <= event[3] <= 0xffffffff:
            raise ValueError('write event is wider than 32 bits')
        if kind == '$':
            if not 0 <= target <= 31:
                raise ValueError('invalid register index')
            if target == 0:
                continue
        result.append(event)
    return result


def describe(event):
    if event is None:
        return '(no event)'
    pc, kind, target, value = event
    where = str(target) if kind == '$' else f'{target:08x}'
    return f'@{pc:08x}: {kind}{where} <= {value:08x}'


def compare(case, text, probes=None):
    errors = []
    expected = parse_log((ROOT/'tests'/case/'expected.log').read_text(encoding='ascii'))
    try:
        actual = parse_log(text)
    except ValueError as error:
        return {'passed':False, 'errors':[str(error)], 'expected_events':len(expected)}
    for index in range(max(len(expected),len(actual))):
        e = expected[index] if index < len(expected) else None
        a = actual[index] if index < len(actual) else None
        if e != a:
            errors.append(f'event {index+1}: expected {describe(e)}; actual {describe(a)}')
            if len(errors) >= 5:
                break
    if 'PHASE_EXECUTE' in text and EVENT.search(text.split('PHASE_EXECUTE')[0]):
        errors.append('write log appeared during reset')
    state_checked = []
    if probes:
        state = json.loads((ROOT/'tests'/case/'final_state.json').read_text(encoding='utf-8'))
        for kind, key, length in [('REG','registers',32),('MEM','nonzero_memory',3072)]:
            if not probes.get(kind):
                continue
            matches = re.findall(r'STATE_'+kind+r' (\d+) ([0-9a-fA-FxXzZ]+)',text)
            if len(matches) != length:
                errors.append(f'missing {kind} state dump: {len(matches)}/{length}')
                continue
            bad = 0
            for index,value in matches:
                index = int(index)
                wanted = state[key][index] if kind == 'REG' else state[key].get(f'{index*4:08x}','00000000')
                if value.lower() != wanted:
                    bad += 1
                    if bad <= 3:
                        errors.append(f'{kind}[{index}]: expected {wanted}; actual {value}')
            state_checked.append(kind)
        if probes.get('PC'):
            match = re.search(r'STATE_PC ([0-9a-fA-FxXzZ]+)',text)
            if not match or match[1].lower() != state['halt_pc']:
                errors.append(f'final PC: expected {state["halt_pc"]}; actual {match[1] if match else "missing"}')
            state_checked.append('PC')
    return {'passed':not errors, 'errors':errors, 'expected_events':len(expected),
            'actual_events':len(actual), 'state_checked':state_checked}


def collect_sources(directory):
    projects = sorted(directory.glob('*.xise'))
    if len(projects) == 1:
        ns = '{http://www.xilinx.com/XMLSchema}'
        tree = ET.parse(projects[0])
        files = [directory/node.attrib[ns+'name'] for node in tree.findall(f'{ns}files/{ns}file')
                 if node.attrib.get(ns+'type') == 'FILE_VERILOG']
    else:
        files = sorted(directory.glob('*.v'))
    if not files or not all(path.is_file() for path in files):
        raise ValueError('Cannot find every Verilog source listed by this project.')
    if len({path.name for path in files}) != len(files):
        raise ValueError('Two source files have the same basename; flattening would lose one.')
    return files


def detect_probes(sources):
    text = {path.name:path.read_text(encoding='utf-8-sig') for path in sources}
    top = next((s for s in text.values() if re.search(r'\bmodule\s+mips\b',s)), '')
    probes = {}
    for module, kind, limit in [('GRF','REG',31),('DM','MEM',3071)]:
        instance = re.search(r'\b'+module+r'\s+(\w+)\s*\(',top)
        body = next((s for s in text.values() if re.search(r'\bmodule\s+'+module+r'\b',s)), '')
        array = re.search(r'\breg\s*\[\s*31\s*:\s*0\s*\]\s+(\w+)\s*\[\s*0\s*:\s*'+str(limit)+r'\s*\]',body)
        if instance and array:
            probes[kind] = f'dut.{instance[1]}.{array[1]}'
    if re.search(r'\bwire\s*\[\s*31\s*:\s*0\s*\]\s+pc\s*;',top):
        probes['PC'] = 'dut.pc'
    return probes


def testbench(cycles, probes):
    dumps = []
    if probes.get('PC'):
        dumps.append(f'$display("STATE_PC %h",{probes["PC"]});')
    if probes.get('REG'):
        dumps.append(f'for(j=0;j<32;j=j+1)$display("STATE_REG %0d %h",j,{probes["REG"]}[j]);')
    if probes.get('MEM'):
        dumps.append(f'for(j=0;j<3072;j=j+1)$display("STATE_MEM %0d %h",j,{probes["MEM"]}[j]);')
    return '''`timescale 1ns/1ps
module tb;
reg clk=0;reg reset=1;integer j;
mips dut(.clk(clk),.reset(reset));
always #5 clk=~clk;
initial begin
 $display("PHASE_RESET");repeat(2)@(posedge clk);@(negedge clk);
 $display("PHASE_EXECUTE");reset=0;
 repeat(%d)@(posedge clk);#1;
 %s
 $finish;
end
endmodule
''' % (cycles, '\n '.join(dumps))


def execute_process(args, cwd, env, timeout=30):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        process = subprocess.run(args,cwd=cwd,env=env,capture_output=True,timeout=timeout,creationflags=flags)
        return process.returncode, (process.stdout+process.stderr).decode('utf-8','replace')
    except subprocess.TimeoutExpired as error:
        return 124, ((error.stdout or b'')+(error.stderr or b'')).decode('utf-8','replace')+'\nTIMEOUT\n'


def compile_cpu(args, cwd, env):
    code,text = execute_process(args,cwd,env)
    if code in (3221225477,-1073741819) and os.name == 'nt':
        # Some Windows Icarus builds crash in a direct child invocation. Retry
        # with literal, single-quoted arguments through a hidden shell process.
        quote = lambda value: "'"+str(value).replace("'","''")+"'"
        command = '& '+' '.join(quote(value) for value in args)+'; exit $LASTEXITCODE'
        encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
        (cwd/'direct_compile_failure.log').write_text(f'exit={code}\n{text}',encoding='utf-8')
        code,text = execute_process(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],cwd,env)
    return code,text


def main(argv=None):
    parser = argparse.ArgumentParser(description='2025 P4 SPE/BRC, CABC, LHBOC local grader')
    parser.add_argument('--cpu',type=Path,default=Path(r'C:\Users\Public\Documents\ISE_projects\CPU_practice'))
    parser.add_argument('--only',type=str.upper,choices=['SPE','BRC','CABC','LHBOC','ALL'],default='ALL')
    parser.add_argument('--case',help='For example SPE/basic or CABC/branch_offsets')
    parser.add_argument('--actual',type=Path,help='Compare an existing ISim/Icarus write log; requires --case')
    parser.add_argument('--iverilog',type=Path)
    parser.add_argument('--state-probe',choices=['auto','off'],default='auto')
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT/'cases.json').read_text(encoding='ascii'))
    if args.actual:
        if not args.case or args.case not in {row['case'] for row in manifest}:
            parser.error('--actual requires an existing --case')
        result = compare(args.case,args.actual.read_text(encoding='utf-8-sig',errors='replace'))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['passed'] else 1
    selected = [row for row in manifest if (not args.case or row['case']==args.case)
                and (args.only=='ALL' or row['group']==('SPE' if args.only=='BRC' else args.only))]
    if not selected:
        parser.error('No selected cases')
    source_files = collect_sources(args.cpu)
    probes = detect_probes(source_files) if args.state_probe=='auto' else {}
    executable = args.iverilog or (Path(shutil.which('iverilog')) if shutil.which('iverilog') else
        ROOT.parent/'output/CPU_Verilog_review_20261104/iverilog_portable/iverilog/bin/iverilog.exe')
    if not executable.is_file():
        raise FileNotFoundError('Icarus not found. Use --iverilog PATH or compare an ISim log with --actual.')
    binary = executable.resolve().parent
    library = binary.parent/'lib/ivl'
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
    run_root = ROOT/'runs'/stamp
    build = run_root/'build';build.mkdir(parents=True)
    source_names = []
    for path in source_files:
        shutil.copyfile(path,build/path.name)
        source_names.append(path.name)
    for parent in {path.parent for path in source_files}:
        for header in parent.glob('*.vh'):
            destination = build/header.name
            if destination.exists() and destination.read_bytes()!=header.read_bytes():
                raise ValueError('Conflicting Verilog include files')
            shutil.copyfile(header,destination)
    (build/'tb.v').write_text(testbench(max(row['cycles'] for row in selected)+8,probes),encoding='utf-8')
    env = dict(os.environ)
    env['PATH'] = str(binary)+os.pathsep+env.get('PATH','')
    env['TMP'] = env['TEMP'] = '.'
    command = [str(executable.resolve())]
    if library.is_dir():
        command += ['-B',os.path.relpath(library,build)]
    command += ['-g2001','-Wall','-s','tb','-o','test.vvp',*source_names,'tb.v']
    code,diagnostics = compile_cpu(command,build,env)
    (build/'compile.log').write_text(diagnostics,encoding='utf-8')
    report = {'cpu':str(args.cpu.resolve()),'run':str(run_root),'probes':probes,
              'compile_exit':code,'diagnostics':diagnostics,'cases':[]}
    if code:
        print(diagnostics or f'Compiler failed with exit code {code}.')
    else:
        vvp = binary/('vvp.exe' if os.name=='nt' else 'vvp')
        for case in selected:
            folder = run_root/case['case'].replace('/','__');folder.mkdir()
            shutil.copyfile(ROOT/'tests'/case['case']/'code.txt',folder/'code.txt')
            invocation = [str(vvp),'-M','-']
            if library.is_dir():
                invocation += ['-M',os.path.relpath(library,folder)]
            invocation.append(os.path.relpath(build/'test.vvp',folder))
            exit_code,text = execute_process(invocation,folder,env)
            (folder/'actual.log').write_text(text,encoding='utf-8')
            result = compare(case['case'],text,probes)
            result.update(case=case['case'],simulation_exit=exit_code)
            result['passed'] = result['passed'] and exit_code==0
            report['cases'].append(result)
            print(('PASS ' if result['passed'] else 'FAIL ')+case['case'])
            for error in result['errors'][:2]:
                print('  '+error)
    passed = code==0 and len(report['cases'])==len(selected) and all(row['passed'] for row in report['cases'])
    report['passed'] = passed
    (run_root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Report: '+str(run_root/'report.json'))
    if not probes:
        print('State probes unavailable: this run compared native write events only.')
    return 0 if passed else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,ET.ParseError) as error:
        print('ERROR: '+str(error),file=sys.stderr)
        raise SystemExit(2)
