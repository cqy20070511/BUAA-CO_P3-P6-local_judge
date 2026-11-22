"""Compare standard BUAA register/memory write logs, ignoring time prefixes."""
from pathlib import Path
import argparse
import re
import sys

PATTERN = re.compile(r'@\s*([0-9a-fA-F]+)\s*:\s*([\$*])\s*([0-9a-fA-F]+)\s*<=\s*([0-9a-fA-FxXzZ]+)')

def parse(text):
    events=[]
    for number,line in enumerate(text.splitlines(),1):
        match=PATTERN.search(line)
        if not match:
            if '@' in line and '<=' in line:raise ValueError(f'line {number}: malformed write event: {line}')
            continue
        pc,kind,target,data=match.groups()
        if any(c in data.lower() for c in 'xz'):raise ValueError(f'line {number}: X/Z in write data: {line}')
        target=int(target,10 if kind=='$' else 16)
        event=(int(pc,16),kind,target,int(data,16))
        if not 0<=event[0]<=0xffffffff or not 0<=event[3]<=0xffffffff:raise ValueError(f'line {number}: value wider than 32 bits')
        if kind=='$' and not 0<=target<=31:raise ValueError(f'line {number}: invalid register number')
        # A CPU may print attempted writes to $0; the architecture discards them.
        if kind=='$' and target==0:continue
        events.append(event)
    return events

def describe(event):
    if event is None:return '(no event)'
    pc,kind,target,data=event
    location=f'${target}' if kind=='$' else f'*{target:08x}'
    return f'@{pc:08x}: {location} <= {data:08x}'

def main(argv=None):
    parser=argparse.ArgumentParser(description='Compare a P4 practice CPU write trace.')
    parser.add_argument('--case',required=True,help='Q01/basic, or an absolute case directory')
    parser.add_argument('--actual',required=True,help='CPU simulation log file')
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parent
    case=Path(args.case)
    if not case.is_absolute():case=root/'tests'/case
    try:
        expected=parse((case/'expected.log').read_text(encoding='utf-8-sig'))
        actual=parse(Path(args.actual).read_text(encoding='utf-8-sig',errors='replace'))
        for index in range(max(len(expected),len(actual))):
            e=expected[index] if index<len(expected) else None
            a=actual[index] if index<len(actual) else None
            if e!=a:
                print(f'FAIL: event {index+1}; expected {len(expected)} events, received {len(actual)}')
                print('expected:',describe(e));print('actual:  ',describe(a))
                return 1
        print(f'PASS: {len(expected)} write events match ({case.parent.name}/{case.name})')
        return 0
    except (OSError,ValueError) as error:
        print('ERROR:',error)
        return 2

if __name__=='__main__':sys.exit(main())
