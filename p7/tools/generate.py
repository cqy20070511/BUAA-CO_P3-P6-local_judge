from pathlib import Path
import json,hashlib,random,sys
from isa import Program,MASK
from reference import reference,hx
ROOT=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
NAMES={'Q01':'syscall','Q02':'teq','Q03':'tltiu','Q04':'kernel_space','Q05':'privileged_instruction','Q06':'EBase','Q07':'withdraw','Q08':'Watch','Q09':'Memory_Limitation','Q10':'monitor','Q11':'Integer_Overflow'}

def warmup(p,seed,memory=True,count=32):
    rng=random.Random(seed)
    for reg in range(1,13):p.li(reg,rng.randrange(1,1000))
    for k in range(count):
        rd,rs,rt=[rng.randrange(1,13) for _ in range(3)]
        name=rng.choice(['and','or','slt','sltu','add'])
        if name=='add':p.emit('andi',rs,rs,0x3fff);p.emit('andi',rt,rt,0x3fff)
        p.emit(name,rd,rs,rt)
        if memory and k%8==0:
            a=0x600+(k%32)*4;p.emit('sw',rd,a,0);p.emit('lw',rd,a,0)
    p.li(5,0x55aa);p.emit('mthi',5);p.emit('mtlo',5)

def fault(p,name,args,slot=0):
    idx=len(p.rows);cont='resume_'+str(idx);p.li(20,0xbadc0ffe);p.fault_return(cont)
    if slot:p.emit('beq' if slot==1 else 'bne',0,0,cont)
    at=p.focus(name,*args)
    p.emit('mtlo',20);p.emit('ori',17,0,(idx&65535)^0x5a5a)
    if getattr(p,'topic','BASE') not in ('Q07','Q09','Q10'):p.emit('sw',20,0x2e80,0)
    p.label(cont);p.emit('mflo',16)
    return at

def bad_pc(p,target):
    cont='badpc_'+str(len(p.rows));p.la(21,cont);p.li(1,target)
    at=p.focus('jr',1);p.emit('ori',4,0,0x1256)
    p.emit('ori',17,0,0xdead);p.label(cont);return at

def irq(case,pc):case['interrupts'].append({'target_pc':hx(pc),'trigger':'first_negedge_macroscopic_pc_match','hold_until':'accepted_m_int_write_7f20_7f23'})

def tail(p,q):
    if q=='Q08':p.cp(19,0)
    elif q=='Q09':p.cp(18,0);p.cp(19,0)
    elif q=='Q10':p.monitor(20,0)
    elif q=='Q11':p.cp(18,0)
    for a in (0x100,0x104,0x2ffc):p.emit('lw',15,a,0)
    p.emit('mfhi',13);p.emit('mflo',14)
    if q in ('Q07','Q08','Q09','Q10','Q11'):
        for n in (18,19):p.emit('mfc0',18,n)
    for n in (1,2,3,4,8,16,17):p.emit('or',18,n,0)

def base_case(n):
    p=Program();g=(n-1)//20;k=(n-1)%20;seed=700000+n
    groups=['运算与全寄存器冒险','访存宽度与字节通道','控制转移与延迟槽','乘除及HI_LO交互','CP0依赖与eret','算术异常与精确提交','数据地址异常与外设权限','取指异常与优先级','外部中断与暂停交叉','双计时器与中断屏蔽']
    c={'id':f'B{n:03}','problem':'BASE','chapter':'00_P7基本CPU强测','title':groups[g]+f' {k+1:02}','seed':seed,'tags':[groups[g]],'interrupts':[],'expected_codes':[]}
    if g==9:return timer_case(p,c,k)
    warmup(p,seed,count=40)
    rng=random.Random(seed)
    if g==0:
        patterns=[0,1,0xffffffff,0x80000000,0x7fffffff,0xffff,0xffff0000,0xaaaaaaaa,0x55555555]
        for rd in range(1,32):
            p.li(rd,patterns[(rd+k)%len(patterns)]);p.emit('or',(rd%31)+1,rd,0)
            p.emit('slt',0,rd,0);p.emit('sltu',((rd+3)%31)+1,rd,0)
            p.emit('and',rd,rd,(rd%31)+1)
        for _ in range(30):
            rd,rs,rt=[rng.randrange(0,32) for _ in range(3)]
            p.emit(rng.choice(['or','and','slt','sltu']),rd,rs,rt)
    elif g==1:
        for phase in range(6):
            addr=[0,0x100,0x2ffc,0x204,0x7fc,0x2ff8][(phase+k)%6]
            value=[0x80ff7f01,0x8000ffff,0x12345678,0xaabbccdd][(phase+k)%4]
            p.li(1,addr+4);p.li(2,value);p.emit('sw',2,-4,1)
            for lane in range(4):p.emit('lb',3,lane-4,1);p.emit('or',4,3,0)
            for off in (-4,-2):p.emit('lh',3,off,1);p.emit('or',4,3,0)
            for lane in range(4):p.emit('sb',3,lane-4,1);p.emit('lw',4,-4,1)
            p.emit('sh',2,-2,1);p.emit('lw',2,-4,1)
        p.li(1,0x100);p.emit('sw',1,0,1);p.emit('lw',1,0,1)
    elif g==2:
        for phase in range(4):
            tag=f'ctl_{phase}';p.emit('jal',tag+'_function');p.emit('or',4,31,0)
            p.jump(tag+'_end');p.label(tag+'_function');p.emit('or',5,31,0)
            p.emit('jr',31);p.emit('ori',6,0,phase+k);p.label(tag+'_end')
            p.li(9,3+(k%4));p.li(10,0);p.label(tag+'_loop');p.emit('addi',9,9,-1)
            p.emit('bne',9,0,tag+'_loop');p.emit('addi',10,10,1)
            p.la(11,tag+'_target');p.emit('sw',11,0x710,0);p.emit('lw',12,0x710,0)
            p.emit('jr',12);p.emit('or',13,12,0);p.emit('ori',17,0,0xdead);p.label(tag+'_target')
    elif g==3:
        c['timing_checks']=[]
        pairs=[(0,7),(0xffffffff,3),(0x80000000,2),(0x7fffffff,0xfffffff9),(0xfffffff3,7),(0xfffffff3,0xfffffff9)]
        for phase in range(8):
            a,b=pairs[(k+phase)%len(pairs)];p.li(1,a);p.li(2,b);producer=p.pc-4
            mdop=['mult','multu','div','divu'][(k+phase)%4];p.emit(mdop,1,2)
            for j in range((k+phase)%5):p.emit('ori',7,0,j)
            consumer=p.emit('mfhi',3);p.emit('mflo',4);p.emit('sw',3,0x900+phase*8,0);p.emit('sw',4,0x904+phase*8,0)
            c['timing_checks'].append({'before_pc':hx(producer),'after_pc':hx(consumer),'minimum_cycles':5 if mdop.startswith('mult') else 10,'purpose':mdop+'规定占用周期的保守下界'})
            if phase%2:p.emit('mthi',4);p.emit('mtlo',3);p.emit('mfhi',6);p.emit('mflo',7)
    elif g==4:
        values=[0,0xfc00,0xfc01,0x1001,0x402,0xffffffff]
        for phase in range(5):
            v=values[(k+phase)%len(values)];p.li(1,v);p.emit('sw',1,0x700,0);p.emit('lw',2,0x700,0)
            p.emit('mtc0',2,12);p.emit('mfc0',3,12);p.emit('or',4,3,0);p.emit('sw',3,0x704,0)
            p.cp(12,2);dest=f'eret_{phase}';p.la(1,dest);p.emit('mtc0',1,14)
            p.emit('mfc0',5,14);p.emit('eret');p.emit('ori',29,0,0xdead)
            p.emit('mtlo',2);p.label(dest);p.emit('mfc0',6,12);p.emit('mflo',7)
        p.cp(12,0)
    elif g==5:
        for phase in range(6):
            p.li(1,0x7fffffff if phase%2==0 else 0x80000000);p.li(2,1)
            op,args=('add',(3,1,2)) if phase%3==0 else ('sub',(3,1,2)) if phase%3==1 else ('addi',(3,1,1 if phase%2==0 else -1))
            if op=='add':p.li(1,0x7fffffff)
            if op=='sub':p.li(1,0x80000000)
            fault(p,op,args,(k+phase)%3);c['expected_codes'].append(12)
            fault(p,'syscall',(),(k+phase+1)%3);c['expected_codes'].append(8)
            fault(p,'raw',(0xffffffff,));c['expected_codes'].append(10)
    elif g==6:
        tests=[('lw',1,4),('lh',3,4),('sw',2,5),('sh',3,5),('lb',0x3000,4),('sb',0x7f0c,5),('lw',0x7f1c,4),('sw',0x7f24,5),('lb',0x7f00,4),('lh',0x7f14,4),('sh',0x7f00,5),('sb',0x7f10,5),('sw',0x7f08,5),('sw',0x7f18,5),('lw',0xffffffff,4),('sw',0x80000000,5)]
        for phase in range(10):
            op,addr,exc=tests[(k+phase)%len(tests)];p.li(1,addr);p.li(2,0x80ffccaa)
            fault(p,op,(0 if k%3==0 and op[0]=='l' else 2,0,1),(k+phase)%3);c['expected_codes'].append(exc)
        p.li(1,0x7fffffff);fault(p,'lw',(2,1,1));c['expected_codes'].append(4)
        p.li(1,0x80000000);fault(p,'sw',(2,-1,1));c['expected_codes'].append(5)
    elif g==7:
        targets=[0x3001,0x3002,0x3003,0x2ffc,0x7000,0xfffffffc,0x7f00]
        for phase in range(7):bad_pc(p,targets[(k+phase)%len(targets)]);c['expected_codes'].append(4)
        cont='lastword_return';p.la(21,cont);p.li(1,0x6ffc);p.focus('jr',1);p.nop();p.label(cont)
        c['expected_codes'].append(8);here=p.pc;p.org(0x6ffc);p.emit('syscall');p.org(here)
    elif g==8:
        p.li(1,17);p.li(2,19);p.li(3,0xaabbccdd);p.emit('sw',3,0x100,0)
        p.cp(12,0x1001 if k>=14 else 0x1003 if k%7==1 else 0x1000 if k%7==2 else 0x1001)
        p.emit('ori',7,0,0x6543)
        if k==14:at=p.focus('mtc0',3,14);c['tags'].append('中断取消mtc0')
        elif k==15:at=p.focus('mfc0',4,12);c['tags'].append('中断取消mfc0')
        elif k==16:p.emit('jal','irq_after');at=p.focus('or',4,31,0);c['tags'].append('jal延迟槽中断')
        elif k==17:p.la(11,'irq_after');p.emit('jr',11);at=p.focus('or',4,3,0);c['tags'].append('jr延迟槽中断')
        elif k==18:p.emit('lw',6,0x100,0);at=p.focus('beq',6,3,'irq_after');p.emit('ori',4,0,0x22);c['tags'].append('load_branch暂停空泡中断')
        elif k==19:at=p.focus('nop');p.emit('multu',1,2);c['tags'].append('中断取消年轻乘法启动')
        elif k%7==0:p.emit('multu',1,2);at=p.focus('mflo',4)
        elif k%7==1:at=p.focus('sw',3,0x104,0)
        elif k%7==2:at=p.focus('mtc0',3,14)
        elif k%7==3:at=fault(p,'syscall',(),k%3);c['expected_codes'].append(8)
        elif k%7==4:at=fault(p,'sw',(3,1,0),k%3);c['expected_codes'].append(5)
        elif k%7==5:p.emit('beq' if k%2 else 'bne',0,0,'irq_after');at=p.focus('or',4,3,0)
        else:at=p.focus('mtlo',3)
        irq(c,at);p.label('irq_after');p.emit('or',8,7,0)
        p.nop(8)
        if k%7 in (1,2):p.cp(12,0x1001)
        p.emit('ori',9,0,0x789a);p.nop(12)
        if k>=10:
            at2=p.focus('sw',3,0x108,0);irq(c,at2);p.nop(12)
        c['expected_codes']=[0]+c['expected_codes']+([0] if k>=10 else [])
        p.cp(12,0)
    tail(p,'BASE');p.finish();p.handler('BASE')
    return p,c

def timer_case(p,c,k):
    warmup(p,c['seed'],count=40)
    which=k%3;mode=(k//3)%2;target=(2 if k in (0,7,12) else 1) if mode==0 else 3
    addresses=[0x7f00] if which==0 else [0x7f10] if which==1 else [0x7f00,0x7f10]
    p.li(20,0);p.li(18,target);p.li(1,17);p.li(2,19)
    sr=0x401 if which==0 else 0x801 if which==1 else 0xc01
    p.cp(12,sr if k<12 or k>=16 else sr&~1)
    preset=80+(k*13)%181
    read_checks=[]
    for a in addresses:
        p.li(3,preset+(a&16));p.emit('sw',3,a+4,0)
        control=(9 if mode==0 else 11) & (7 if k>=16 else 15)
        p.li(3,control|(0xdead0000 if k%4==0 else 0));p.emit('sw',3,a,0)
    p.nop(8)
    for a in addresses:
        at=p.emit('lw',8,a+8,0);read_checks.append({'pc':hx(at),'reg':8,'minimum':1,'maximum':preset+(a&16),'purpose':'Count已装载且开始递减'})
        at=p.emit('lw',9,a+4,0);read_checks.append({'pc':hx(at),'reg':9,'minimum':preset+(a&16),'maximum':preset+(a&16),'purpose':'Preset读回'})
        at=p.emit('lw',10,a,0);read_checks.append({'pc':hx(at),'reg':10,'minimum':control,'maximum':control,'purpose':'CTRL低四位与保留位读回'})
    if k>=12:
        p.nop(preset+40);p.cp(12,sr)
    if k>=16:
        p.label('timer_allow_irq')
        for a in addresses:p.li(3,9 if mode==0 else 11);p.emit('sw',3,a,0)
    p.label('timer_wait');p.emit('beq',20,18,'timer_done');p.nop()
    if k>=6:p.emit('multu',1,2);p.emit('mflo',7)
    p.jump('timer_wait');p.label('timer_done')
    for a in (0x7f00,0x7f10):p.emit('sw',0,a,0)
    p.nop(8);p.emit('lw',5,0x7f00,0);p.emit('lw',6,0x7f10,0);p.emit('sw',20,0x2e00,0)
    for a in addresses:
        at=p.emit('lw',8,a+8,0);read_checks.append({'pc':hx(at),'reg':8,'minimum':0,'maximum':preset+(a&16),'purpose':'停止计数后的Count合法范围'})
    p.finish();p.org(0x4180);p.emit('mfc0',26,13);p.emit('mfc0',27,14)
    p.emit('mfhi',22);p.emit('mflo',23);p.emit('addi',20,20,1)
    restart=(mode==0 and target>1)
    p.emit('bne',20,18,'timer_restart' if restart else 'timer_return');p.nop()
    for a in addresses:p.emit('sw',0,a,0)
    if restart:
        p.jump('timer_return');p.label('timer_restart');p.li(17,9)
        for a in addresses:p.emit('sw',17,a,0)
    p.label('timer_return');p.emit('eret');p.emit('ori',29,0,0xdead)
    c.update({'oracle_mode':'timer_contract','timer_read_checks':read_checks,'timer':{'which':which,'mode':mode,'preset':preset,'interrupt_count':target,'enable_after_expiry':k>=12,'ctrl_irq_gate_test':k>=16},'tags':c['tags']+[f'模式{mode}',f'Timer{which}' if which<2 else '双Timer','动态EPC与循环次数']})
    return p,c

def reset_case(n):
    p=Program();k=n-201;seed=800000+n
    c={'id':f'B{n:03}','problem':'BASE','chapter':'00_P7基本CPU强测','title':'运行中复位与二次启动 '+str(k+1),'seed':seed,'tags':['运行中复位','GRF_HI_LO_CP0重新初始化','复位优先级'],'interrupts':[],'expected_codes':[]}
    p.emit('or',30,31,0)
    for reg in range(31):p.emit('or',31,reg,0)
    p.emit('mfhi',28);p.emit('mflo',29);p.emit('mfc0',26,12);p.emit('mfc0',27,13);p.emit('mfc0',28,14)
    warmup(p,seed,count=40);p.cp(12,0xfc00);p.cp(14,0x34567891)
    p.li(1,0xffffffed);p.li(2,7)
    if k%8==0:target=p.focus('multu',1,2);p.emit('mfhi',3);p.emit('mflo',4)
    elif k%8==1:target=p.focus('div',1,2);p.emit('mfhi',3);p.emit('mflo',4)
    elif k%8==2:p.emit('divu',1,2);target=p.focus('mflo',4)
    elif k%8==3:target=p.focus('sw',1,0x100,0);p.emit('lw',4,0x100,0)
    elif k%8==4:p.emit('sw',1,0x100,0);p.emit('lw',4,0x100,0);target=p.focus('beq',4,1,'reset_branch');p.nop();p.label('reset_branch')
    elif k%8==5:target=p.focus('mtc0',1,14);p.emit('mfc0',4,14)
    else:
        fault(p,'syscall',(),k%3);c['expected_codes']=[8];target=0x4184 if k%8==6 else 0x41ac
    tail(p,'BASE');p.finish();p.handler('BASE')
    c['mid_reset']={'target_pc':hx(target),'trigger':'first_negedge_macroscopic_pc_match','hold_posedges':3,'interrupt_during_reset':int(k>=8),'compare_epoch':'after_second_reset_release','external_dm_reset':'clear_all_3072_words'}
    return p,c

def pending_case(n):
    p=Program();k=n-217;seed=800000+n
    c={'id':f'B{n:03}','problem':'BASE','chapter':'00_P7基本CPU强测','title':'待决IP持续更新与屏蔽 '+str(k+1),'seed':seed,'tags':['Cause_IP','IE_IM_EXL屏蔽','解除屏蔽响应','中断响应后IP清除'],'interrupts':[],'expected_codes':[0]}
    warmup(p,seed,count=40)
    state=[0x1000,0x0001,0x1003,0xec01,0xfc00,0x0003,0x0000,0xfc03][k]
    p.cp(12,state);at=p.focus('or',3,1,0);irq(c,at);p.nop(16)
    p.emit('mfc0',3,13);p.emit('mfc0',4,12);p.cp(12,0x1001)
    p.nop(16);p.emit('mfc0',6,13);p.cp(12,0);tail(p,'BASE');p.finish();p.handler('BASE')
    return p,c

def topic(q,n):
    p=Program();p.topic=q;k=n-1;seed=int(q[1:])*10000+n
    c={'id':f'{q}-{n:02}','problem':q,'chapter':'01_课上考试P7','title':'','seed':seed,'tags':[NAMES[q]],'interrupts':[],'expected_codes':None}
    warmup(p,seed,memory=q!='Q07',count=24)
    c['tags']+=['独立复位','混合前序指令']
    if q=='Q01':
        p.li(2,[1,4,10,0,0xffffffff,0x80000000][k%6]);p.li(3,0x1234)
        if k>=18:p.cp(12,0x1001)
        if k in (6,7,8):p.emit('sw',3,0x700,0);p.emit('lw',4,0x700,0)
        if k in (9,10,11):p.emit('multu',3,5)
        at=fault(p,'syscall',(),k%3)
        if k>=18:irq(c,at)
        c['title']=f'syscall 参数{[1,4,10,0,0xffffffff,0x80000000][k%6]:08x} '+['普通位置','成立分支延迟槽','不成立分支延迟槽'][k%3]
        c['expected_codes']=([0] if k>=18 else [])+[8]
    elif q=='Q02':
        pairs=[(0,0),(1,1),(0xffffffff,0xffffffff),(0x80000000,0x80000000),(0x7fffffff,0x7fffffff),(0x12345678,0x12345678),(0,1),(1,0),(0x80000000,0),(0xffffffff,0x7fffffff),(0x11223344,0x11223345),(0xffff,0xffff0000)]
        a,b=pairs[k%12];p.li(1,a);p.li(2,b)
        if k>=12:p.emit('sw',2,0x700,0);p.emit('lw',2,0x700,0)
        rs,rt=(1,1) if k==22 else (0,0) if k==23 else (1,2)
        fault(p,'teq',(rs,rt),k%3)
        c['title']=f'teq {a:08x}/{b:08x} '+('load紧邻供数' if k>=12 else '立即供数')
        c['expected_codes']=[13] if (a==b or k in (22,23)) else []
    elif q=='Q03':
        pairs=[(0,0),(0xffffffff,0),(0,1),(1,1),(0x7ffe,0x7fff),(0x7fff,0x7fff),(0x7fff,0x8000),(0x80000000,0x8000),(0xffff7fff,0x8000),(0xffff8000,0x8000),(0xfffffffe,0xffff),(0xffffffff,0xffff)]
        a,imm=pairs[k%12];p.li(1,a)
        if k>=12:p.emit('mtlo',1);p.emit('mflo',1)
        fault(p,'tltiu',(1,imm),k%3)
        c['title']=f'tltiu rs={a:08x} imm={imm:04x} '+('HI_LO供数' if k>=12 else 'GRF供数')
        bound=imm|0xffff0000 if imm&0x8000 else imm;c['expected_codes']=[13] if a<bound else []
    elif q=='Q04':
        table=[('lw',0x7f00,False),('lw',0x7f10,False),('sw',0x7f04,False),('sw',0x7f14,False),('sb',0x7f20,False),('lw',0x3000,False),('lw',0x2ffc,False),('sw',0,False),('lw',0x7f00,True),('lw',0x7f10,True),('sw',0x7f04,True),('sw',0x7f14,True)]
        if k<12:
            op,a,kernel=table[k];p.li(1,a);p.li(2,0x1234)
            if kernel:p.cp(12,2)
            fault(p,op,(2,0,1),k%3)
            if kernel:p.cp(12,0)
            invalid=not kernel and (a>=0x3000);c['expected_codes']=[4 if op[0]=='l' else 5] if invalid else []
            c['title']=f'{"内核态" if kernel else "用户态"} {op} {a:04x}'
        else:
            target=[0x4180,0x4280,0x417c,0x6ffc,0x4181,0x7000][(k-12)%6]
            if target in (0x4180,0x4280,0x6ffc):
                bad_pc(p,target);c['expected_codes']=[4]
                if target==0x4280:here=p.pc;p.org(target);p.emit('raw',0xffffffff);p.org(here)
            elif target==0x417c:
                cont='user_border';p.la(21,cont);p.li(1,target);p.focus('jr',1);p.nop();p.label(cont)
                here=p.pc;p.org(target);p.emit('syscall');p.org(here);c['expected_codes']=[8]
            else:bad_pc(p,target);c['expected_codes']=[4]
            c['title']=f'用户取指边界 {target:08x}'
    elif q=='Q05':
        modes=[0,0x10000000,2,0x10000002]
        state=modes[k%4];p.cp(12,state);p.li(1,0x10000000)
        op='mfc0' if (k//4)%2==0 else 'mtc0';rd=12 if k<16 else 14
        fault(p,op,(1,rd),k%3);c['title']=f'CU0={(state>>28)&1} EXL={(state>>1)&1} {op} CP0[{rd}]'
        c['expected_codes']=[10] if state==0 else []
        if k in (20,21):
            # Legal mtc0 clears CU0 based on its old state, then the next read traps.
            p.cp(12,0x10000000);p.fault_return('after_clear');p.emit('mtc0',0,12);p.focus('mfc0',2,12);p.label('after_clear')
            c['expected_codes'].append(10)
    elif q=='Q06':
        bases=[0x4180,0x4280,0x4300,0x5ffc,0x6e00];entry=bases[k%5]
        p.emit('mfc0',1,15);p.cp(15,entry)
        if k%4==1:p.cp(15,bases[(k+1)%5]);entry=bases[(k+1)%5]
        if k>=18:p.cp(12,0x1001)
        at=fault(p,'lw' if k%2 else 'syscall',(2,3,0) if k%2 else (),k%3)
        if k>=18:irq(c,at)
        c['expected_codes']=([0] if k>=18 else [])+[4 if k%2 else 8]
        c['title']=f'异常入口 {entry:04x} '+('连续改写' if k%4==1 else 'mfc0读回')
        c['extra_handler']=entry
    elif q=='Q07':
        titles=['无sw且空区间','无sw但区间有效','单次恢复旧整字','低地址零','DM末字','两次同地址sw','不同地址最近sw','sb不覆盖sw记录','sh不覆盖sw记录','连续撤销两次','修改下界排除','上界相等排除','左边界包含','右边界不包含','mfc0读取记录','mtc0修改界限紧邻','load供给sw','sw地址数据同源','中断撤销sw的记录','延迟槽撤销','不成立槽撤销','越界sw不建立记录','sw后读回再撤销','两次sw两次撤销']
        addr=0 if k==3 else 0x2ffc if k==4 else 0x100
        p.cp(18,0 if k==0 else 0x3000);p.cp(19,0)
        if k>=2:
            p.li(1,0x11223344);p.emit('sw',1,addr,0)
            p.li(2,0xaabbccdd);p.emit('sw',2,addr,0)
            if k in (5,6,23):p.li(3,0x778899aa);p.emit('sw',3,addr+(4 if k==6 else 0),0)
            if k==7:p.emit('sb',1,addr+1,0)
            if k==8:p.emit('sh',1,addr+2,0)
            if k==10:p.cp(19,addr+4)
            if k in (11,13):p.cp(18,addr)
            if k==12:p.cp(19,addr);p.cp(18,addr+4)
            if k==14:p.emit('mfc0',7,20);p.emit('mfc0',8,21)
            if k==15:p.cp(18,addr+4);p.cp(19,addr)
            if k==16:p.emit('lw',2,addr,0);p.emit('sw',2,addr,0)
            if k==17:p.li(1,addr);p.emit('sw',1,0,1)
            if k==18:
                p.cp(12,0x1001);p.li(4,0xdeadbeef);at=p.focus('sw',4,addr+4,0);irq(c,at)
            if k==21:
                fault(p,'sw',(2,1,0));c['expected_codes']=[5]
            if k==22:p.emit('lw',6,addr,0)
        at=fault(p,'withdraw',(),1 if k==19 else 2 if k==20 else 0)
        if k in (9,23):fault(p,'withdraw',())
        c['title']=titles[k]
        if c['expected_codes'] is None:c['expected_codes']=([0] if k==18 else [])+([5] if k in (10,11,13) else [])
    elif q=='Q08':
        p.li(2,0x80ff7f01);p.emit('sw',2,0x100,0)
        forms=[('lw',0x100,0x101),('lb',0x100,0x101),('lb',0x101,0x101),('lh',0x100,0x101),('lh',0x102,0x101),('sw',0x100,0x103),('sh',0x102,0x103),('sb',0x103,0x103),('lw',0x101,0x101),('sw',0x101,0x101),('lb',0x7f00,0x7f00),('sw',0x7f08,0x7f08)]
        if k<12:
            op,a,watch=forms[k];p.cp(18,watch);p.cp(19,1+(4 if op[0]=='l' else 2));p.li(1,a)
            fault(p,op,(3,0,1),k%3);size={'lw':4,'sw':4,'lh':2,'sh':2,'lb':1,'sb':1}[op]
            ordinary=(a%size!=0) or a>=0x7f00
            c['expected_codes']=[4 if op[0]=='l' else 5] if ordinary else [23] if a<=watch<a+size else []
            c['title']=f'{op} {a:04x} 监视字节{watch:04x}'
        else:
            op=['multu','mthi','syscall','raw','add','lw'][(k-12)%6]
            p.emit('watchpc',19,'watch_focus');p.emit('ori',19,19,0x101);p.emit('mtc0',19,18)
            enable=0 if k==18 else 1 if k==19 else 0xffffffff if k==20 else 9;p.cp(19,enable)
            p.li(1,0x7fffffff);p.li(2,1);p.fault_return('watch_resume');p.label('watch_focus')
            args={'multu':(1,2),'mthi':(1,),'syscall':(),'raw':(0xffffffff,),'add':(3,1,2),'lw':(3,1,0)}[op]
            p.focus(op,*args);p.emit('mtlo',5);p.label('watch_resume')
            c['expected_codes']=[23] if enable&9==9 else []
            c['title']=f'IMWatch优先级与精确异常 {op} enable={enable:08x}'
    elif q=='Q09':
        forms=[('lw',0x100,0x100,0x104,0),('sw',0x100,0x100,0x104,1),('lw',0x100,0x100,0x104,1),('sw',0x100,0x100,0x104,0),('sb',0x100,0x101,0x103,1),('sh',0x100,0x101,0x103,1),('sw',0x100,0x101,0x103,1),('lb',0x103,0x101,0x103,0),('lh',0x102,0x101,0x103,0),('lw',0x100,0x102,0x102,0),('sw',0x100,0x102,0x102,1),('lw',0x2ffc,0x2fff,0x3000,0)]
        op,a,low,high,odd=forms[k%12];p.li(2,0xaabbccdd);p.emit('sw',2,0x100,0)
        highbits=1 if odd else 3
        p.cp(18,(highbits<<16)|low);p.cp(19,high)
        if k>=12:
            # Same parity with high bits in both registers; raw readback is checked.
            p.cp(18,((highbits^0x8000)<<16)|low);p.cp(19,0x80000000|high)
        p.li(1,a);fault(p,op,(3 if op[0]=='l' else 2,0,1),k%3)
        size={'lw':4,'sw':4,'lh':2,'sh':2,'lb':1,'sb':1}[op];bad=(low<high and a<high and a+size>low and ((op[0]=='s' and odd) or (op[0]=='l' and not odd)))
        c['expected_codes']=[5 if op[0]=='s' else 4] if bad else []
        c['title']=f'{op} {a:04x} 区间[{low:04x},{high:04x}) '+('只读' if odd else '只写')
    elif q=='Q10':
        enables=[0,0x80000001,0x00030001,0xffff0000,0x0000ffff,0x80000000]
        en=enables[k%6];hi,low=0x104,0x100
        if k in (6,7):hi=0x103
        if k in (8,9):hi=low
        p.li(2,0xaabbccdd);p.emit('sw',2,0x100,0)
        p.monitor(18,hi);p.monitor(19,low);p.monitor(20,en)
        if k>=12:
            rd=18 if k%4==0 else 19 if k%4==1 else 12 if k%4==2 else 20
            val=low-1 if rd==18 else hi+1 if rd==19 else 0x1001
            p.li(1,val);fault(p,'monitor',(1,rd),k%3);bad=rd in (18,19)
            c['title']=f'monitor 写CP0[{rd}]={val:08x}';c['expected_codes']=[5] if bad else []
        else:
            op='sb' if k==10 else 'sh' if k==11 else 'sw';addr=0x104 if k in (3,4) else 0x100
            at=fault(p,op,(2,addr,0),k%3)
            enabled=(en>>16).bit_count()>(en&65535).bit_count();bad=op=='sw' and enabled and not (low<=addr and addr+3<hi)
            c['title']=f'{op} {addr:04x} 区间[{low:04x},{hi:04x}) enable={en:08x}';c['expected_codes']=[5] if bad else []
        p.emit('mtc0',2,18);p.emit('mfc0',8,18)
    elif q=='Q11':
        params=[('add',5,5,10,3),('add',5,6,10,3),('add',-5,-5,10,3),('add',-5,-6,10,3),('addi',0,0,0,3),('addi',0,1,0,3),('sub',5,15,10,5),('sub',5,16,10,5),('add',0x7fffffff,1,0x7fff,0),('add',0x7fffffff,1,0x7fff,1),('add',0x7fffffff,1,0x7fff,3),('sub',0x80000000,0x7fffffff,10,5)]
        op,a,b,bound,ctrl=params[k%12]
        if k>=12:ctrl^=6  # independently enable the other instruction category
        p.cp(19,bound);p.cp(18,ctrl);p.li(1,a);p.li(2,b)
        if k in (18,19,20):p.emit('sw',2,0x700,0);p.emit('lw',2,0x700,0)
        args=(3,1,b) if op=='addi' else (3,1,2);fault(p,op,args,k%3)
        from reference import signed
        full=signed(a)-signed(b) if op=='sub' else signed(a)+(b if op=='addi' else signed(b));v=full&MASK
        enabled=ctrl&1 and ctrl&(4 if op=='sub' else 2);bad=enabled and (not -(1<<31)<=full<(1<<31) or abs(signed(v))>bound)
        c['expected_codes']=[12] if bad else []
        c['title']=f'{op} a={a&MASK:08x} b={b&MASK:08x} 开关{ctrl:x} 阈值{bound}'
    tail(p,q);p.finish();p.handler(q)
    if q=='Q06' and c['extra_handler']!=0x4180:p.handler(q,c['extra_handler'],'_alt')
    return p,c

def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def save(p,c):
    c['finish_pc']=hx(p.labels['finish']);c['max_cycles']=12000
    c['reset']={'posedge_cycles':3,'dm_initial':'all_zero','interrupt_initial':0}
    c['encoding']='book_practice';c['focus_pcs']=[hx(x) for x in p.foci]
    c['labels']={k:hx(v) for k,v in p.labels.items()}
    words=p.words()
    directory=ROOT/'tests'/c['chapter']/(c['problem'] if c['problem']!='BASE' else '')/c['id']
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'code.txt').write_text(''.join(hx(x)+'\n' for x in words),encoding='ascii')
    (directory/'program.asm').write_text(p.listing(),encoding='utf-8')
    if c.get('oracle_mode')=='timer_contract':
        wait=p.labels.get('timer_allow_irq',p.labels['timer_wait']);done=p.labels['timer_done'];count=c['timer']['interrupt_count']
        expected={'mode':'timer_contract','final_registers':{'5':'00000000','6':'00000000','20':hx(count),'29':'00000000','30':'0000cafe'},'final_memory':{'00002e00':hx(count)},'handler_entries':count,'cause_register':26,'epc_register':27,'cause_exccode':0,'allowed_epc_min':hx(wait),'allowed_epc_max':hx(done-4),'eret_poison_pc':hx(max(p.rows)),'external_ack_count':0,'note':'Timer周期、循环次数和动态EPC按协议约束检查，不捏造固定逐条日志。'}
        expected['read_checks']=c['timer_read_checks']
        expected['min_handler_gap_cycles']=max(1,c['timer']['preset']-16) if c['timer']['interrupt_count']>1 and c['timer']['which']<2 else 0
    else:
        expected=reference(words,c)
        actual=[e['code'] for e in expected['exceptions']]
        if c['expected_codes'] is not None and actual!=c['expected_codes']:raise AssertionError((c['id'],c['title'],'intended',c['expected_codes'],'oracle',actual))
        (directory/'expected_grf.log').write_text(''.join(f'@{e["pc"]}: ${e["reg"]} <= '+(' or '.join(e['allowed_values']) if 'allowed_values' in e else e['value'])+'\n' for e in expected['grf']),encoding='ascii')
        (directory/'expected_dm.log').write_text(''.join(f'@{e["pc"]}: *{e["aligned_address"]} <= {e["merged_word"]}\n' for e in expected['dm']),encoding='ascii')
    write_json(directory/'expected.json',expected);write_json(directory/'case.json',c);write_json(directory/'interrupts.json',c['interrupts'])
    return {k:c[k] for k in ('id','problem','chapter','title','tags','finish_pc')}|{'directory':str(directory.relative_to(ROOT)).replace('\\','/'),'oracle_mode':expected['mode'],'instructions':expected.get('instructions'),'exceptions':len(expected.get('exceptions',[])),'sha256_code':hashlib.sha256((directory/'code.txt').read_bytes()).hexdigest()}

def main():
    out=[]
    for n in range(1,201):
        p,c=base_case(n);out.append(save(p,c))
    for n in range(201,217):
        p,c=reset_case(n);out.append(save(p,c))
    for n in range(217,225):
        p,c=pending_case(n);out.append(save(p,c))
    for q in NAMES:
        for n in range(1,25):
            p,c=topic(q,n);out.append(save(p,c))
    write_json(ROOT/'raw_cases.json',out)
    write_json(ROOT/'problems.json',{'BASE':{'name':'P7基本CPU强测','count':224},**{q:{'name':name,'count':24} for q,name in NAMES.items()}})
    print(f'Generated {len(out)} cases: 224 BASE + 11*24; exact={sum(x["oracle_mode"]=="exact" for x in out)} timer_contract={sum(x["oracle_mode"]=="timer_contract" for x in out)}',flush=True)
if __name__=='__main__':main()
