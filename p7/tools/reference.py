"""Instruction-level oracle; no submitted RTL, assembler rows or DUT values used."""
MASK=0xffffffff
def signed(v,bits=32):
    v&=(1<<bits)-1;return v-(1<<bits) if v>>(bits-1) else v
def hx(v):return f'{v&MASK:08x}'
def reference(words,case,mutation=None):
    q=case['problem'];r=[0]*32;c=[0]*32;c[12]=0x10000000 if q=='Q05' else 0
    if q=='Q06':c[15]=0x4180
    mem=bytearray(0x3000);timers={0x7f00:0,0x7f04:0,0x7f08:0,0x7f10:0,0x7f14:0,0x7f18:0}
    pc=0x3000;pending=None;hi=lo=0;has_sw=False;active=False;fired=set();grf=[];dm=[];ints=[];exceptions=[];trace=[];hist={};visits={};hilo_choices={}
    def read(a,n):
        if a<0x3000:return int.from_bytes(mem[a:a+n],'little')
        return timers.get(a,0)
    def reg(dst,value):
        if dst:
            r[dst]=value&MASK;event={'pc':hx(pc),'reg':dst,'value':hx(value)}
            if dst in hilo_choices and pc in (0x4188,0x418c):
                options=hilo_choices.pop(dst)
                if len(options)>1:event['allowed_values']=options
            grf.append(event)
    def store(a,n,v):
        nonlocal active
        lane=a&3;be=((1<<n)-1)<<lane;bits=(v&((1<<(8*n))-1))<<(8*lane);mask=((1<<(8*n))-1)<<(8*lane)
        event={'pc':hx(pc),'address':hx(a),'aligned_address':hx(a&~3),'byteen':be,'value_mask':hx(mask),'write_bits':hx(bits)}
        if a<0x3000:
            mem[a:a+n]=(v&((1<<(8*n))-1)).to_bytes(n,'little');event['merged_word']=hx(read(a&~3,4));dm.append(event)
        elif 0x7f20<=a<0x7f24:
            ints.append(event);active=False
        else:
            timers[a]=v&(15 if a&15==0 else MASK)
    def trap(code,bd,kind):
        nonlocal pc,pending
        c[12]|=2;c[13]=(c[13]&0x0000fc00)|(int(bd)<<31)|(code<<2);c[14]=(pc-4 if bd else pc)&MASK
        exceptions.append({'victim_pc':hx(pc),'epc':hx(c[14]),'bd':int(bd),'code':code,'kind':kind})
        pc=c[15] if q=='Q06' and mutation!='fixed_ebase' else 0x4180;pending=None
    for step in range(30000):
        visits[pc]=visits.get(pc,0)+1
        for i,event in enumerate(case.get('interrupts',[])):
            if i not in fired and pc==int(event['target_pc'],16):active=True;fired.add(i)
        c[13]=(c[13]&~0xfc00)|(0x1000 if active else 0)
        bd=pending is not None;next_target=pending;pending=None
        trace.append(hx(pc))
        if active and c[12]&1 and not c[12]&2 and c[12]&0x1000:
            if mutation!='ignore_interrupt':
                hilo_choices.clear()
                victim=words[(pc-0x3000)//4] if pc%4==0 and 0x3000<=pc<0x7000 else 0
                if victim>>26==0 and victim&63 in (17,19):
                    dst=22 if victim&63==17 else 23
                    old=hi if dst==22 else lo;new=r[(victim>>21)&31]
                    hilo_choices[dst]=sorted({hx(old),hx(new)})
                trap(0,False if mutation=='drop_bd' else bd,'interrupt');continue
        if pc&3 or not 0x3000<=pc<0x7000:
            if c[12]&2:raise ValueError('handler fetch error '+hex(pc))
            trap(4,bd,'exception');continue
        ins=words[(pc-0x3000)//4];op=ins>>26;rs=(ins>>21)&31;rt=(ins>>16)&31;rd=(ins>>11)&31;fn=ins&63
        a,b=r[rs],r[rt];imm=signed(ins&65535,16);addr=(a+imm)&MASK
        code=0;actions=[];target=None;direct=None;name='unknown'
        load=op in (0x20,0x21,0x23);st=op in (0x28,0x29,0x2b);n={0x20:1,0x21:2,0x23:4,0x28:1,0x29:2,0x2b:4}.get(op,0)
        if q=='Q04' and mutation!='ignore_kernel' and not c[12]&2 and 0x4180<=pc<=0x7fff:code=4
        if q=='Q08' and not code and c[19]&9==9 and pc==(c[18]>>16):code=23
        if op==0:
            if ins==0:name='nop'
            elif fn in (0x20,0x22):
                name='add' if fn==0x20 else 'sub';full=signed(a)+signed(b) if fn==0x20 else signed(a)-signed(b);v=full&MASK
                ov=not -(1<<31)<=full<(1<<31)
                if q=='Q11':ov=bool(c[18]&1 and c[18]&(2 if fn==0x20 else 4) and (ov or (abs(signed(v))>=(c[19]&65535) if mutation=='overflow_ge' else abs(signed(v))>(c[19]&65535))))
                if ov and mutation!='ignore_overflow':code=code or 12
                actions.append(('reg',rd,v))
            elif fn in (0x24,0x25,0x2a,0x2b):
                name={0x24:'and',0x25:'or',0x2a:'slt',0x2b:'sltu'}[fn]
                v=(a&b) if fn==0x24 else (a|b) if fn==0x25 else int(signed(a)<signed(b)) if fn==0x2a else int(a<b)
                actions.append(('reg',rd,v))
            elif fn==8:name='jr';target=a
            elif fn in (0x10,0x12):name='mfhi' if fn==16 else 'mflo';actions.append(('reg',rd,hi if fn==16 else lo))
            elif fn in (0x11,0x13):name='mthi' if fn==17 else 'mtlo';actions.append((name,a))
            elif fn in (0x18,0x19,0x1a,0x1b):
                name={24:'mult',25:'multu',26:'div',27:'divu'}[fn]
                if fn in (24,25):v=(signed(a)*signed(b)) if fn==24 else a*b;actions.append(('hilo',(v>>32)&MASK,v&MASK))
                else:
                    aa,bb=(signed(a),signed(b)) if fn==26 else (a,b)
                    if not bb:raise ValueError('division by zero in generated data')
                    quotient=(abs(aa)//abs(bb))*(-1 if (aa<0)!=(bb<0) else 1)
                    actions.append(('hilo',(aa-quotient*bb)&MASK,quotient&MASK))
            elif fn==12:name='syscall';code=code or (10 if mutation=='syscall_as_ri' else 8)
            elif fn==52 and q=='Q02':name='teq';code=code or (13 if (a!=b if mutation=='teq_not_equal' else a==b) else 0)
            else:code=code or 10
        elif op in (8,12,13,15):
            name={8:'addi',12:'andi',13:'ori',15:'lui'}[op]
            if op==8:
                full=signed(a)+imm;v=full&MASK;ov=not -(1<<31)<=full<(1<<31)
                if q=='Q11':ov=bool(c[18]&3==3 and (ov or (abs(signed(v))>=(c[19]&65535) if mutation=='overflow_ge' else abs(signed(v))>(c[19]&65535))))
                if ov and mutation!='ignore_overflow':code=code or 12
            else:v=(a&(ins&65535)) if op==12 else (a|(ins&65535)) if op==13 else ((ins&65535)<<16)
            actions.append(('reg',rt,v))
        elif op in (4,5):
            name='beq' if op==4 else 'bne';taken=(a==b) if op==4 else (a!=b)
            target=(pc+4+imm*4)&MASK if taken else pc+8
        elif op==3:name='jal';target=((pc+4)&0xf0000000)|((ins&0x3ffffff)<<2);actions.append(('reg',31,pc+8))
        elif op==16:
            if ins==0x42000018:name='eret';actions.append(('eret',));direct=c[14]
            elif rs in (0,4):
                name='mfc0' if rs==0 else 'mtc0'
                if q=='Q05' and mutation!='ignore_privilege' and not c[12]&2 and not c[12]&(1<<28):code=code or 10
                if rs==0:actions.append(('reg',rt,c[rd]))
                else:actions.append(('cp',rd,b))
            else:code=code or 10
        elif op==1 and q=='Q03' and rt==11:
            name='tltiu';v=(ins&65535) if mutation=='tltiu_zero_extend' else imm&MASK
            if a<v:code=code or 13
        elif ins==0x04000000 and q=='Q07':
            name='withdraw'
            if has_sw:
                if not c[19]<=c[20]<c[18]:code=code or 5
                else:actions.append(('store',c[20],4,c[21]))
        elif op==30 and q=='Q10':
            name='monitor'
            if (rd==18 and b<c[19]) or (rd==19 and b>c[18]):code=code or 5
            elif rd in (18,19,20):actions.append(('monitor',rd,b))
        elif load or st:
            name={0x20:'lb',0x21:'lh',0x23:'lw',0x28:'sb',0x29:'sh',0x2b:'sw'}[op]
            bad=(addr%n!=0 and mutation!='ignore_alignment') or not (addr+n<=0x3000 or 0x7f00<=addr and addr+n<=0x7f0c or 0x7f10<=addr and addr+n<=0x7f1c or 0x7f20<=addr and addr+n<=0x7f24)
            bad=bad or (not -(1<<31)<=signed(a)+imm<(1<<31))
            timer=(0x7f00<=addr<0x7f0c or 0x7f10<=addr<0x7f1c)
            bad=bad or (timer and (n!=4 or (st and addr&15==8)))
            bad=bad or (q=='Q04' and mutation!='ignore_kernel' and not c[12]&2 and 0x4180<=addr<=0x7fff)
            if bad:code=code or (4 if load else 5)
            if q=='Q08' and not code and c[19]&1 and ((load and c[19]&4) or (st and c[19]&2)):
                watched=c[18]&65535
                if (addr==watched if mutation=='watch_start_only' else addr<=watched<addr+n):code=23
            if q=='Q09' and not code:
                lower,upper=c[18]&65535,c[19]&65535
                only_read=((c[18]>>16).bit_count()+(c[19]>>16).bit_count())&1
                overlap=lower<=addr<upper if mutation=='limit_start_only' else lower<upper and addr<upper and addr+n>lower
                if overlap and ((st and only_read) or (load and not only_read)):code=5 if st else 4
            if q=='Q10' and st and n==4 and not code and ((c[20]>>16).bit_count()>=(c[20]&65535).bit_count() if mutation=='monitor_ge' else (c[20]>>16).bit_count()>(c[20]&65535).bit_count()):
                if addr<c[19] or addr+3>=c[18]:code=5
            if not code:
                if load:
                    v=read(addr,n);v=signed(v,n*8) if n<4 else v
                    actions.append(('reg',rt,v))
                else:
                    if q=='Q07' and n==4 and addr<0x3000:actions.append(('snapshot',addr,b if mutation=='withdraw_use_new' else read(addr,4)))
                    actions.append(('store',addr,n,b))
        else:code=code or 10
        hist[name]=hist.get(name,0)+1
        if code and not c[12]&2:
            trap(code,False if mutation=='drop_bd' else bd,'exception');continue
        if code and c[12]&2:raise ValueError(f'generated handler fault {name} {pc:08x} code={code}')
        for action in actions:
            if action[0]=='reg':reg(action[1],action[2])
            elif action[0]=='store':store(*action[1:])
            elif action[0]=='mthi':hi=action[1]
            elif action[0]=='mtlo':lo=action[1]
            elif action[0]=='hilo':hi,lo=action[1:]
            elif action[0]=='eret':c[12]&=~2
            elif action[0]=='snapshot':has_sw=True;c[20],c[21]=action[1:]
            elif action[0]=='monitor':c[action[1]]=action[2]
            elif action[0]=='cp':
                regno,value=action[1:]
                if regno==12:c[12]=value&(0x1000fc03 if q=='Q05' else 0xfc03)
                elif regno==14 or q=='Q06' and regno==15:c[regno]=value
                elif q=='Q07' and regno in (18,19):c[regno]=value
                elif q in ('Q08','Q09','Q11') and regno in (18,19):c[regno]=value&(65535 if q=='Q11' and regno==19 else MASK)
        if pc==int(case['finish_pc'],16):
            assert r[30]==0xcafe
            break
        if direct is not None:pc=direct;pending=None
        else:pc=(next_target if bd else pc+4)&MASK;pending=target
    else:raise ValueError(f'oracle did not terminate {case["id"]} pc={pc:08x}')
    final_options={}
    for event in grf:
        if 'allowed_values' in event:final_options[str(event['reg'])]=event['allowed_values']
        else:final_options.pop(str(event['reg']),None)
    return {'mode':'exact','grf':grf,'dm':dm,'int':ints,'exceptions':exceptions,'final_register_options':final_options,
            'final_registers':[hx(v) for v in r],'final_hilo':[hx(hi),hx(lo)],
            'final_cp0':{str(k):hx(c[k]) for k in (12,13,14,18,19,20,21)},
            'final_memory':{hx(a):hx(read(a,4)) for a in range(0,0x3000,4) if read(a,4)},
            'instructions':step+1,'histogram':hist,'fired_interrupts':len(fired),'trace':trace}
