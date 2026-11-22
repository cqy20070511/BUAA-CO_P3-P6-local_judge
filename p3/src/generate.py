"""Build the statements, ROM images and independent Python reference traces.
Only the standard library is needed. Generated tests never modify a user's CPU.
"""
from pathlib import Path
import argparse, hashlib, json, random, re, struct

ROOT = Path(__file__).resolve().parent.parent
MASK = 0xffffffff
BASE = 0x3000
SEED = 20261029

# id, mnemonic, title, format, opcode, funct, origin, precise exercise definition
DEFS = [
('E01','xor','按位异或','R',0,0x26,'标准指令；2021 同类题', 'R[rd] = R[rs] XOR R[rt]。'),
('E02','srl','逻辑右移','S',0,2,'基础热身', 'R[rd] = R[rt] 逻辑右移 shamt 位，高位补 0；shamt 为 0～31。'),
('E03','sltu','无符号比较','R',0,0x2b,'基础热身', '按 32 位无符号数比较；R[rs] < R[rt] 时 R[rd]=1，否则 R[rd]=0。'),
('E04','movz','条件传送','R',0,0x0a,'2020 回忆；采用标准 movz 语义', '若 R[rt]=0，则 R[rd]=旧 R[rs]；否则不写任何寄存器，RegWrite 必须为 0。'),
('E05','wsbh','半字内部交换相邻字节','U',0,0x2c,'2020 Roife', '把源值的四个字节 A B C D（从高到低）变为 B A D C，写入 rd。例如 0x12345678 变为 0x34127856；不是四字节倒序。'),
('E06','gray','整字格雷码转换','U',0,0x2d,'2021 P3/P4 记录', 'R[rd] = R[rs] XOR (R[rs] 逻辑右移 1 位)。'),
('E07','clo','前导一计数','U',0,0x30,'2019 首测回忆的题型', '从 R[rs] 的 bit31 向 bit0 连续统计 1，遇到首个 0 停止，计数写入 rd。全 1 返回 32；最高位为 0 返回 0。'),
('E08','flog2','无符号整数对数','U',0,0x31,'2019 重测回忆的题型', '若 R[rs]=0，R[rd]=0；否则 R[rd]=floor(log2(unsigned(R[rs])))，即最高有效 1 的位编号（0～31）。0x80000000 返回 31。'),
('E09','slo','左移并在低位补一','S',0,0x32,'2021 FlyingLandlord', 'R[rd] = (旧 R[rt] << shamt) OR (2^shamt-1)，截取低 32 位。shamt=0 时原样传送；补一掩码为 0。'),
('E10','qaq','平方后按位与','R',0,0x33,'2023 qaq', '分别计算 R[rs] 和 R[rt] 的平方，各取低 32 位，再按位与，结果写入 rd。乘法溢出丢弃高位。'),
('E11','ssze','后导零比较','R',0,0x34,'2021 文章的同类题', '定义 tz(x) 为从 bit0 开始连续的 0 的个数，tz(0)=32。若 tz(R[rs])=tz(R[rt])，则 R[rd]=1；否则 R[rd]=R[rs]-R[rt]，按低 32 位回绕。'),
('E12','balr','相对跳转并写指定链接寄存器','L',0x30,None,'2020 balr', '无条件执行 nextPC=PC+4+(SE16(imm)<<2)，同时 R[rt]=PC+4。rs 字段固定为 0。rt=0 时仍跳转，但 $0 不变。'),
('E13','bltzalr','负数条件跳转并链接','I',0x31,None,'2020 bltzalr 的明确化练习版', '按有符号数判断旧 R[rs]<0：成立时跳到 PC+4+(SE16(imm)<<2)，并写 R[rt]=PC+4；不成立时 nextPC=PC+4，且不写寄存器。本题明确规定仅跳转时链接。'),
('E14','bezal','零值条件寄存器跳转并链接','B',0,0x35,'2021 bezal', '若旧 R[rt]=0，则 nextPC=旧 R[rs]，并写 R[31]=PC+4；否则顺序执行且不写寄存器。即使 rs=31，跳转目标也必须取写回之前的值。'),
('E15','booez','按两段位数奇偶性分支','I',0x32,None,'2023 booez', '若旧 R[rs] 的低 16 位中 1 的个数为奇数，且旧 R[rt] 的高 16 位中 0 的个数为偶数，则按 beq 的方式相对跳转；否则顺序执行。0 个也属于偶数。不写 GRF 和 DM。'),
('E16','cwp','由立即数与 PC 比较选择写入目标','I',0x33,None,'2024 cwp', '令 u=ZE16(imm)。按无符号数比较 (u<<8) 与当前指令的 PC：严格大于时 R[rs]=u，否则 R[rt]=u。写入数据始终是 u，不是 u<<8，也不是 PC+4。'),
('E17','bgc','两位分组格雷码计数分支','I',0x34,None,'2024 bgc', '把旧 R[rs] 分成 16 组两位数，每组按 00→00、01→01、10→11、11→10 转为格雷码。统计转换后总共多少个 1；总数严格大于 rt 字段的整数值（0～31）时，按 beq 的方式相对跳转。不读取 R[rt] 作为阈值，不写 GRF/DM。'),
('E18','csws','按符号选择存储数据','M',0x35,None,'2023 csws；另一份笔记拼为 cwsw', 'EA=旧 R[base]+SE16(offset)。若旧 R[rt] 的 bit31=1，Mem32[EA]=旧 R[rt]；否则 Mem32[EA]=0。两种情况都要写内存，MemWrite 均为 1；不写 GRF。'),
('E19','lwor','带寄存器编号偏移的加载','M',0x36,None,'2021 lwor / lword 回忆', 'EA=(旧 R[base]+SE16(offset)+4*rt) AND 0x0000007c；rt 在地址公式中是指令字段的整数编号，不是 R[rt]。R[rt]=Mem32[EA]。先完成加法的低 32 位回绕，再按位与。'),
('E20','lbi','加载并替换一个对应位置字节','M',0x37,None,'2020 lbi', 'EA=旧 R[base]+SE16(offset)，k=EA AND 3，W=Mem32[EA AND 0xfffffffc]，mask=0xff<<(8*k)。R[rt]=(旧 R[rt] AND ~mask) OR (W AND mask)。仅替换第 k 个字节，其他三个字节保持不变；不做符号扩展。'),
('E21','lwso','由源寄存器及数据奇偶性选择写入目标','M',0x38,None,'2024 lwso', '先取 v=旧 R[rt]，h=v AND 15，left=(v<<h) AND 31，right=(v逻辑右移h) AND 31。EA=旧 R[base]+SE16(offset)，W=Mem32[EA]。W 的 bit0=1 时写 R[left]=W，否则写 R[right]=W。计算目标编号时一律使用写回前的 v。'),
('E22','jas','跳转并把返回地址存入内存','J',0x39,None,'2021 jas；公开描述不完整，补全为练习规则', 'Mem32[旧 R[29]]=PC+4；nextPC={(PC+4)[31:28],target[25:0],00}。不写 GRF，不修改 R[29]。本练习保留完整 PC 和 IM 范围，不采用旧记录的 PC 对 128 取模。'),
('E23','bal','无条件分支并链接到 $31','L',1,None,'2019 bal；采用无延迟槽练习规则', 'nextPC=PC+4+(SE16(imm)<<2)，同时 R[31]=PC+4。rs 固定 00000，rt 字段固定 10001。'),
('E24','lbu','无符号字节加载','M',0x24,None,'2019 lbu；标准指令', 'EA=旧 R[base]+SE16(offset)，读取该字节并零扩展到 32 位，写入 R[rt]。'),
('E25','lb','有符号字节加载','M',0x20,None,'字节访存热身；标准指令', 'EA=旧 R[base]+SE16(offset)，读取该字节并按 bit7 符号扩展到 32 位，写入 R[rt]。'),
]
D = {r[1]: dict(zip(('id','name','title','fmt','op','fun','origin','definition'),r)) for r in DEFS}
BY_ID = {v['id']:v for v in D.values()}
EDGES = [0,1,2,3,0xffffffff,0xfffffffe,0x7fffffff,0x80000000,0x80000001,0xffff,0xffff0000,0x12345678,0x87654321,0x55555555,0xaaaaaaaa,0xffffff00]
EXAMPLES = {
'xor':('R[1]=0x0000f0f0，R[2]=0x00003333，rd=3','R[3]=0x0000c3c3'),
'srl':('R[2]=0x80000000，shamt=1，rd=3','R[3]=0x40000000'),
'sltu':('R[1]=0xffffffff，R[2]=1，rd=3','R[3]=0（无符号比较）'),
'movz':('R[1]=0x12345678，R[2]=0，rd=3','R[3]=0x12345678；若 R[2]=1 则 RegWrite=0'),
'wsbh':('R[2]=0x12345678，rd=3','R[3]=0x34127856'),
'gray':('R[1]=0x80000000，rd=3','R[3]=0xc0000000'),
'clo':('R[1]=0xf0000000，rd=3','R[3]=4；全 1 则返回 32'),
'flog2':('R[1]=0x80000000，rd=3','R[3]=31；源值为 0 时返回 0'),
'slo':('R[2]=0x12345678，shamt=4，rd=3','R[3]=0x2345678f'),
'qaq':('R[1]=3，R[2]=5，rd=3','R[3]=9，因为 9 AND 25 = 9'),
'ssze':('R[1]=12，R[2]=20，rd=3','两数都有 2 个后导 0，R[3]=1；若改成 8 和 12 则为 0xfffffffc'),
'balr':('PC=0x3000，rt=5，imm=2','nextPC=0x300c，R[5]=0x3004'),
'bltzalr':('PC=0x3000，R[1]=0xffffffff，rt=5，imm=2','nextPC=0x300c，R[5]=0x3004；源值改为 0 时不链接'),
'bezal':('PC=0x3000，R[1]=0x3080，R[2]=0','nextPC=0x3080，R[31]=0x3004'),
'booez':('R[1]=1，R[2]=0xffff0000','两个条件成立：低段有 1 个 1，高段有 0 个 0；发生分支'),
'cwp':('PC=0x3000，rs=1，rt=2','imm=0x30 时 R[2]=0x30；imm=0x31 时 R[1]=0x31'),
'bgc':('R[1]=0xaaaaaaaa，rt 字段=31','每组 10 变成 11，总计 32 个 1，32>31，发生分支'),
'csws':('EA=0x100，原内存为非零值','R[rt]=0x80000001 时存该值；R[rt]=7 时覆盖为 0；两者 MemWrite 都为 1'),
'lwor':('R[base]=0，rt 字段=3，offset=0','EA=12；读取 Mem32[12] 写入 R[3]，与 R[3] 旧值无关'),
'lbi':('Mem32[0]=0x89abcdef，旧 R[2]=0x12345678，EA=1','R[2]=0x1234cd78，其他三个字节保留'),
'lwso':('旧 R[rt]=0x23，因此 h=3、left=24、right=4','加载到奇数 5 时写 R[24]=5；加载到偶数 6 时写 R[4]=6'),
'jas':('PC=0x3000，R[29]=0x100，跳转目标=0x3080','Mem32[0x100]=0x3004，nextPC=0x3080，R[29] 不变'),
'bal':('PC=0x3000，imm=1','nextPC=0x3008，R[31]=0x3004'),
'lbu':('Mem32[0]=0x89abcdef，EA=0，rt=2','R[2]=0x000000ef'),
'lb':('Mem32[0]=0x89abcdef，EA=0，rt=2','R[2]=0xffffffef'),
}

def sext16(v): return (v&0x7fff)-(v&0x8000)
def signed(v): return v if v<0x80000000 else v-(1<<32)
def pop(v): return bin(v&MASK).count('1')
def tz(v): return 32 if v==0 else (v&-v).bit_length()-1
def enc(name,rd=0,rs=0,rt=0,imm=0,sh=0):
    if name=='nop': return 0
    if name in ('add','sub'): return rs<<21|rt<<16|rd<<11|({'add':32,'sub':34}[name])
    if name in ('ori','lui','lw','sw','beq'): return dict(ori=13,lui=15,lw=35,sw=43,beq=4)[name]<<26|rs<<21|rt<<16|(imm&65535)
    d=D[name];op=d['op'];f=d['fmt']
    if f in ('R','S','U','B'):
        if f=='U': rs,rt=(0,rs) if name=='wsbh' else (rs,0)
        if f=='S':rs=0
        if f=='B':rd=0
        return op<<26|rs<<21|rt<<16|rd<<11|sh<<6|d['fun']
    if f=='J': return op<<26|(imm&0x3ffffff)
    if name=='bal':rs,rt=0,17
    if name=='balr':rs=0
    return op<<26|rs<<21|rt<<16|(imm&65535)

def decode(w):
    op=w>>26;fun=w&63
    if w==0:return 'nop'
    if op==0 and fun in (32,34):return 'add' if fun==32 else 'sub'
    if op in (13,15,35,43,4):return {13:'ori',15:'lui',35:'lw',43:'sw',4:'beq'}[op]
    for d in D.values():
        if op==d['op'] and (d['fun'] is None or fun==d['fun']):return d['name']
    raise ValueError(f'unknown instruction {w:08x}')

def assembly(w,pc):
    n=decode(w);rs=w>>21&31;rt=w>>16&31;rd=w>>11&31;sh=w>>6&31;u=w&65535
    if n=='nop':return n
    if n in ('add','sub','xor','sltu','movz','qaq','ssze'):return f'{n} ${rd}, ${rs}, ${rt}'
    if n in ('srl','slo'):return f'{n} ${rd}, ${rt}, {sh}'
    if n in ('wsbh','gray','clo','flog2'):return f'{n} ${rd}, ${rt if n=="wsbh" else rs}'
    if n=='ori':return f'ori ${rt}, ${rs}, 0x{u:04x}'
    if n=='lui':return f'lui ${rt}, 0x{u:04x}'
    if n in ('lw','sw','csws','lwor','lbi','lwso','lbu','lb'):return f'{n} ${rt}, {sext16(u)}(${rs})'
    if n=='bezal':return f'bezal ${rs}, ${rt}'
    if n=='cwp':return f'cwp ${rs}, ${rt}, 0x{u:04x}'
    if n=='jas':return f'jas L_{(((pc+4)&0xf0000000)|((w&0x3ffffff)<<2)):08x}'
    target=f'L_{(pc+4+sext16(u)*4)&MASK:08x}'
    if n=='bal':return f'bal {target}'
    if n=='balr':return f'balr ${rt}, {target}'
    return f'{n} ${rs}, ${rt}, {target}'

def reference(words,limit=1200,bounded=False):
    r=[0]*32;mem=[0]*3072;pc=BASE;trace=[];hits={}
    for cycle in range(limit):
        idx=(pc-BASE)//4
        if pc&3 or not 0<=idx<len(words):
            if pc==BASE+4*len(words):return trace,hits
            raise ValueError(f'undefined pc {pc:08x}')
        w=words[idx];name=decode(w);hits[name]=hits.get(name,0)+1
        rs=w>>21&31;rt=w>>16&31;rd=w>>11&31;sh=w>>6&31;u=w&65535;im=sext16(u);a=r[rs];b=r[rt]
        nxt=(pc+4)&MASK;rw=0;ra=rt;data=0;mw=0;ma=0;md=0;load=0;dest=0
        if name in ('add','sub','xor','sltu','ssze','qaq','movz'):
            rw=1;ra=rd
            if name=='add':data=a+b
            elif name=='sub':data=a-b
            elif name=='xor':data=a^b
            elif name=='sltu':data=int(a<b)
            elif name=='ssze':data=1 if tz(a)==tz(b) else a-b
            elif name=='qaq':data=(a*a&MASK)&(b*b&MASK)
            elif name=='movz':rw=int(b==0);data=a
        elif name in ('srl','slo'):
            rw=1;ra=rd;data=b>>sh if name=='srl' else (b<<sh)|((1<<sh)-1)
        elif name in ('wsbh','gray','clo','flog2'):
            rw=1;ra=rd
            if name=='wsbh':data=((b&0x00ff00ff)<<8)|((b&0xff00ff00)>>8)
            elif name=='gray':data=a^(a>>1)
            elif name=='clo':data=32-((~a)&MASK).bit_length()
            else:data=max(0,a.bit_length()-1)
        elif name=='ori':rw=1;data=a|u
        elif name=='lui':rw=1;data=u<<16
        elif name in ('beq','booez','bgc','bal','balr','bltzalr'):
            take=name in ('bal','balr')
            if name=='beq':take=a==b
            elif name=='booez':take=pop(a&65535)%2==1 and (16-pop(b>>16))%2==0
            elif name=='bgc':take=sum(pop(((a>>(2*k))&3)^(((a>>(2*k))&3)>>1)) for k in range(16))>rt
            elif name=='bltzalr':take=signed(a)<0
            if take:nxt=(pc+4+im*4)&MASK
            if name in ('bal','balr','bltzalr') and take:rw=1;ra=31 if name=='bal' else rt;data=pc+4
        elif name=='bezal':
            if b==0:rw=1;ra=31;data=pc+4;nxt=a
        elif name=='cwp':rw=1;ra=rs if (u<<8)>pc else rt;data=u
        elif name in ('lw','sw','csws','lwor','lbi','lwso','lbu','lb','jas'):
            ma=(r[29] if name=='jas' else a+im)&MASK
            if name=='lwor':ma=(ma+4*rt)&0x7c
            if ma>0x2fff or (name not in ('lbi','lbu','lb') and ma&3):raise ValueError(f'{name} bad EA {ma:08x}')
            word=mem[ma//4]
            if name in ('sw','csws','jas'):
                mw=1;md=(pc+4 if name=='jas' else b if name=='sw' or b&0x80000000 else 0)&MASK
                if name=='jas':nxt=((pc+4)&0xf0000000)|((w&0x3ffffff)<<2)
            else:
                load=1;rw=1;data=word
                if name=='lbi':m=255<<((ma&3)*8);data=(b&(~m&MASK))|(word&m)
                elif name in ('lbu','lb'):
                    data=(word>>((ma&3)*8))&255
                    if name=='lb' and data&128:data|=0xffffff00
                elif name=='lwso':
                    h=b&15;ra=((b<<h) if word&1 else (b>>h))&31
        elif name!='nop':raise AssertionError(name)
        data&=MASK
        # Disabled data/address buses are don't-cares; RegWrite to $0 may be suppressed.
        row=[cycle,pc,w,nxt,rw,ra,data,mw,ma,md,load,name]
        if rw and ra:r[ra]=data
        if mw:mem[ma//4]=md
        r[0]=0;pc=nxt
        reg_hash=hashlib.sha256(struct.pack('<32I',*r)).hexdigest()
        mem_hash=hashlib.sha256(struct.pack('<3072I',*mem)).hexdigest()
        trace.append(row+[reg_hash,mem_hash])
    if bounded:return trace,hits
    raise ValueError('unexpected nontermination')

class Program:
    def __init__(self):self.words=[];self.lines=[];self.fixups=[];self.labels={}
    def add(self,name,**kw):
        self.words.append(enc(name,**kw));self.lines.append(name+' '+', '.join(f'{k}={v:#x}' for k,v in kw.items()));return self
    def li(self,r,v):
        self.add('lui',rt=r,imm=(v>>16)&65535);self.add('ori',rt=r,rs=r,imm=v&65535);return self
    def mark(self,l):self.labels[l]=len(self.words);return self
    def branch(self,name,label,**kw):
        self.fixups.append((len(self.words),name,label,kw));return self.add(name,**kw)
    def finish(self):
        for i,name,l,kw in self.fixups:
            kw=dict(kw);kw['imm']=(BASE+4*self.labels[l])>>2 if name=='jas' else self.labels[l]-i-1
            self.words[i]=enc(name,**kw);self.lines[i]=name+' -> '+l+' '+str(kw)
        if not 0<len(self.words)<=1024:raise AssertionError(len(self.words))
        return self
    def setup(self,rng):
        for r in range(1,32):self.li(r,rng.getrandbits(32))
        return self
    def memory(self):
        # Distinct nonzero bytes; both parities and signs; preserve $28 as test data, not a base convention.
        for a in range(0,128,4):
            self.li(28,((0x8132a578^(a*0x01030701))+(a//4&1))&MASK);self.add('sw',rs=0,rt=28,imm=a)
        for a in (0x2ff8,0x2ffc):self.li(28,0x80ff7f01^(a&4));self.add('sw',rs=0,rt=28,imm=a)
        return self

CASES=[]
def save_case(ex,name,p,bounded=False,limit=1200,reset='none'):
    p.finish();trace,hits=reference(p.words,limit,bounded)
    if not trace:raise AssertionError(name)
    if ex!='BASE' and not hits.get(BY_ID[ex]['name']):raise AssertionError('exercise never executed '+name)
    folder=ROOT/'tests'/ex/name;folder.mkdir(parents=True,exist_ok=True)
    (folder/'program.hex').write_text('v2.0 raw\n'+''.join(f'{w:08x}\n' for w in p.words),encoding='utf-8')
    # Source is assembled by MarsExport, which installs this booklet's instruction masks.
    (folder/'program.asm').write_text('.text 0x3000\n'+''.join(f'L_{BASE+4*i:08x}: {assembly(w,BASE+4*i)}\n' for i,w in enumerate(p.words))+f'L_{BASE+4*len(p.words):08x}:\n',encoding='utf-8')
    (folder/'listing.txt').write_text('PC        HEX       32-BIT BINARY                    INSTRUCTION\n'+''.join(f'{BASE+4*i:08x}  {w:08x}  {w:032b}  {assembly(w,BASE+4*i)}\n' for i,w in enumerate(p.words)),encoding='utf-8')
    header='cycle\tpc\tInstr\tnextPC\tRegWrite\tRegAddr\tRegData\tMemWrite\tMemAddr\tMemData\tload\tinstruction\tregisters_sha256\tmemory_sha256\n'
    def rowtext(row):return '\t'.join(str(x) if i in (0,4,5,7,10) else f'{x:08x}' if i in (1,2,3,6,8,9) else str(x) for i,x in enumerate(row))+'\n'
    (folder/'expected.tsv').write_text(header+''.join(map(rowtext,trace)),encoding='utf-8')
    CASES.append([ex,name,str(folder.relative_to(ROOT)).replace('\\','/'),len(trace),reset,sum(v for k,v in hits.items() if k in D)])

def branch_case(name,a,b,rt=2,imm_direction='forward'):
    p=Program().li(1,a).li(2,b)
    if name=='bgc':p.li(rt,0x13579bdf) if rt else None
    kw=dict(rs=1,rt=rt)
    # Taken and not-taken paths write distinguishable values; backward/self cases are deliberately bounded.
    if imm_direction=='forward':
        p.branch(name,'target',**kw).li(3,0x12340001).mark('target').li(4,0x56780002).add('sw',rs=0,rt=3,imm=256).add('sw',rs=0,rt=4,imm=260)
        return p,False,1200
    p.mark('target').add('ori',rt=4,rs=4,imm=0x40)
    if imm_direction=='self':p.mark('target2');p.branch(name,'target2',**kw)
    else:p.branch(name,'target',**kw)
    p.add('sw',rs=0,rt=4,imm=260)
    return p,True,len(p.words)+8

def build_tests():
    rng=random.Random(SEED)
    # These can be run immediately on the user's current eight-instruction baseline.
    p=Program().setup(rng)
    for n in range(96):p.add('add' if n%2==0 else 'sub',rd=rng.randrange(32),rs=rng.randrange(32),rt=rng.randrange(32))
    for a in (0,4,0x2ffc):p.add('sw',rs=0,rt=7,imm=a).add('lw',rs=0,rt=8,imm=a)
    save_case('BASE','baseline',p)
    for mode in ('low','high','across_rising'):save_case('BASE','reset_'+mode,Program().setup(rng).memory().add('nop'),reset=mode)
    for name in ('xor','srl','sltu','movz','wsbh','gray','clo','flog2','slo','qaq','ssze'):
        ex=D[name]['id'];fmt=D[name]['fmt']
        values=EDGES+[(1<<k) for k in range(32)]+[(MASK^(MASK>>k)) for k in range(33)]
        p=Program().setup(rng)
        for i,a in enumerate(values):
            b=values[(i*17+3)%len(values)];p.li(1,a).li(2,b)
            if name=='movz' and i%2==0:p.li(2,0)
            p.add(name,rs=1,rt=2,rd=3,sh=i%32 if fmt=='S' else 0)
            p.add('sw',rs=0,rt=3,imm=256)
        save_case(ex,'edges',p)
        p=Program().setup(rng)
        for i in range(32):
            if name=='movz':p.li(2,0 if i%2==0 else 1)
            p.add(name,rs=i,rt=2,rd=i,sh=i if fmt=='S' else 0)
            p.add(name,rs=1,rt=i,rd=0,sh=i if fmt=='S' else 0)
            p.add(name,rs=0,rt=0,rd=(i+1)%32,sh=i if fmt=='S' else 0)
        save_case(ex,'alias_and_zero',p)
        for k in range(3):
            p=Program().setup(rng)
            for i in range(80):
                if name=='movz' and i%3==0:p.li(2,0)
                p.add(name,rs=rng.randrange(32),rt=(2 if name=='movz' and i%3==0 else rng.randrange(32)),rd=rng.randrange(32),sh=rng.randrange(32) if fmt=='S' else 0)
            save_case(ex,'random_'+str(k+1),p)
    for name in ('booez','bgc','bltzalr'):
        ex=D[name]['id']
        pairs=[(1,0,2),(0,0,2),(1,0xffff0000,2),(1,0x7fff0000,2),(0x80000000,0,2),(0xffffffff,0xffffffff,2),(0xaaaaaaaa,0,31),(0x55555555,1,16),(0xffffffff,1,15),(0,1,0)]
        for i,(a,b,rt) in enumerate(pairs):
            for direction in ('forward','backward','self'):
                p,bounded,lim=branch_case(name,a,b,rt,direction);save_case(ex,f'condition_{i:02d}_{direction}',p,bounded,lim)
        # bltzalr may overwrite its own condition/target register; use captured old operands.
        if name=='bltzalr':
            for rt in (0,1,31):
                p=Program().li(1,MASK);p.branch(name,'target',rs=1,rt=rt).li(3,999).mark('target').add('sw',rs=0,rt=1,imm=256)
                save_case(ex,'link_register_'+str(rt),p)
    for name in ('balr','bal'):
        ex=D[name]['id']
        for rt in ([0,1,2,31] if name=='balr' else [17]):
            p=Program().setup(rng);p.branch(name,'target',rt=rt).li(3,999).mark('target').add('sw',rs=0,rt=(rt if name=='balr' else 31),imm=256)
            save_case(ex,'forward_link_'+str(rt),p)
            for off in (-1,-2,0):
                p=Program().add('nop').add(name,rt=rt,imm=off).add('nop');save_case(ex,'offset_'+str(off)+'_r'+str(rt),p,True,12)
    for rs in (1,31):
        for value in (0,1,MASK):
            p=Program().setup(rng);p.li(2,value);p.li(rs,BASE+4*(len(p.words)+4));p.add('bezal',rs=rs,rt=2).add('ori',rt=5,rs=0,imm=55).add('sw',rs=0,rt=31,imm=256)
            save_case('E14',f'rs{rs}_condition_{value:08x}',p)
    for i,imm in enumerate([0,1,0x2f,0x30,0x31,0x32,0x33,0x34,0x35,0x7fff,0x8000,0xffff]+list(range(64))):
        p=Program().li(1,0x11223344).li(2,0x55667788)
        for rs,rt in ((1,2),(0,2),(1,0),(1,1)):
            p.add('cwp',rs=rs,rt=rt,imm=imm).add('sw',rs=0,rt=1,imm=256).add('sw',rs=0,rt=2,imm=260)
        save_case('E16',f'imm_{i:02d}_{imm:04x}',p)
    # Memory classes initialize the DM using only existing lui/ori/sw.
    for name in ('csws','lwor','lbi','lwso','lbu','lb'):
        ex=D[name]['id']
        p=Program().setup(rng).memory()
        addrs=range(16) if name in ('lbi','lbu','lb') else range(0,128,4)
        for a in addrs:
            p.li(1,8).li(2,0x1234567f)
            p.add(name,rs=1,rt=2,imm=a-8).add('sw',rs=0,rt=2,imm=256)
        save_case(ex,'lanes_and_offsets',p)
        p=Program().setup(rng).memory()
        for a in ([0,1,2,3,0x2ffc,0x2ffd,0x2ffe,0x2fff] if name in ('lbi','lbu','lb') else [0,4,0x2ff8,0x2ffc]):
            for base in (0,4,MASK-3):
                off=a-base if base<0x80000000 else a+4
                if -32768<=off<=32767:
                    p.li(1,base).li(2,0x80ab7f01).add(name,rs=1,rt=2,imm=off)
                    p.add(name,rs=1,rt=0,imm=off)
        save_case(ex,'address_boundaries',p)
        p=Program().setup(rng).memory()
        for rt in range(32):
            p.li(1,0x40);p.add(name,rs=1,rt=rt,imm=-4)
        save_case(ex,'register_numbers',p)
        if name=='csws':
            p=Program().memory()
            for v in EDGES:p.li(2,v).add('csws',rs=0,rt=2,imm=260).add('lw',rs=0,rt=3,imm=260)
            save_case(ex,'both_paths_overwrite_nonzero',p)
        if name=='lwor':
            p=Program().memory()
            for rt in range(32):
                for base in (0,0xfffffff0,0x7ffffffc):p.li(1,base).li(rt,0x76543210).add('lwor',rs=1,rt=rt,imm=-32768)
            save_case(ex,'mask_and_wrap',p)
        if name=='lbi':
            p=Program().memory()
            for a in range(4):p.li(2,0x12345678).add('lbi',rs=0,rt=2,imm=a).add('sw',rs=0,rt=2,imm=256)
            p.li(2,0).add('lbi',rs=2,rt=2,imm=3)
            save_case(ex,'preserve_three_bytes_and_alias',p)
        if name=='lwso':
            for parity in (0,1):
                p=Program().memory().li(28,0x80000000|parity).add('sw',rs=0,rt=28,imm=0)
                for v in range(64):p.li(2,v).add('lwso',rs=0,rt=2,imm=0)
                save_case(ex,'destination_parity_'+str(parity),p)
            p=Program().memory().li(28,0x81234567).add('sw',rs=0,rt=28,imm=0).li(2,0).add('lwso',rs=2,rt=2,imm=0)
            save_case(ex,'base_equals_rt',p)
    for a in (0,4,0x2ffc):
        p=Program().setup(rng).li(29,a);p.branch('jas','target').li(3,0xdeadbeef).mark('target').add('lw',rs=29,rt=2).add('sw',rs=0,rt=2,imm=256)
        save_case('E22','stack_'+str(a),p)
    p=Program().li(29,0x100).mark('again');p.branch('jas','again');save_case('E22','self_jump',p,True,8)
    # Include a long forward jump so PC/4 or a short ROM address cannot accidentally pass.
    p=Program().li(29,0x104);p.branch('jas','far')
    for i in range(140):p.add('nop')
    p.mark('far').add('lw',rs=29,rt=2);save_case('E22','far_target',p)

def fmt(d):
    f=d['fmt'];op=f"{d['op']:06b}";fun='—' if d['fun'] is None else f"{d['fun']:06b}"
    if f=='R':bits=f'{op} rs rt rd 00000 {fun}';syntax=f"{d['name']} $rd, $rs, $rt"
    elif f=='S':bits=f'{op} 00000 rt rd shamt {fun}';syntax=f"{d['name']} $rd, $rt, shamt"
    elif f=='U':
        bits=f'{op} 00000 rt rd 00000 {fun}' if d['name']=='wsbh' else f'{op} rs 00000 rd 00000 {fun}'
        syntax=f"{d['name']} $rd, $"+('rt' if d['name']=='wsbh' else 'rs')
    elif f=='B':bits=f'{op} rs rt 00000 00000 {fun}';syntax='bezal $rs, $rt'
    elif f=='L':bits=f'{op} 00000 '+('10001' if d['name']=='bal' else 'rt')+' imm16';syntax='bal label' if d['name']=='bal' else 'balr $rt, label'
    elif f=='J':bits=f'{op} target26';syntax='jas label'
    else:bits=f'{op} rs rt imm16';syntax=f"{d['name']} $rt, offset($base)" if f=='M' else f"{d['name']} $rs, $rt, "+('imm16' if d['name']=='cwp' else 'label')
    return op,fun,bits,syntax

def documents():
    intro='''# P3 加指令练习合集

版本 1.0，2026-10-29。根据已找到的 2019、2020、2021、2023、2024 年题型整理，共 25 题。每题可在原来的八指令 CPU 上独立实现，也可累计实现；题目之间不要求依赖。现成的 jal、addiu、sll 等可以保留，但评测不依赖它们。

**这是统一规则后的练习版，不是官方原题重印。自定义编码、缺失条件和边界定义以本册为准。** xor、srl、sltu、movz、bal、lbu、lb 保留标准编码；其余题统一重新分配编码，避免题目互相冲突。特别是本册 clo、wsbh 的编码也为练习所用，不能直接当成标准 MIPS 编码查表。Controller 的内部 type 编号由你自行选择，不必等于 OP/FUN。

## 全部题目共用的规则

- 基础指令：`add, sub, ori, lw, sw, beq, lui, nop`；加减溢出按低 32 位回绕。
- 无延迟槽。当前指令 PC 为 P 时，链接值为 **P+4**。一般指令 nextPC=P+4；仅题面指定跳转才改变。
- PC 异步复位到 0x3000，IM 为 4096×32；DM 字节地址范围 0x0000～0x2fff，3072 个字。GRF 复位为 0，$0 永远为 0。
- `R[rs]` 是寄存器内容；没有方括号的 rs/rt/rd 是 5 位字段表示的编号。所有源值、条件和目标地址均使用该条指令执行前的值。
- SE16 表示 16→32 位符号扩展；ZE16 表示零扩展。所有加减乘移位结果最后取低 32 位。逻辑右移高位补 0。
- 使用小端字节序：例如 Mem32[0]=0x89abcdef，则地址 0、1、2、3 的字节依次为 ef、cd、ab、89。
- lw/sw/csws/lwso/jas 的最终字地址必须四字节对齐，且在 0～0x2ffc；lbi/lbu/lb 允许任意有效字节地址；lwor 先按题面算最终 EA 再检查，结果始终落在 0～0x7c。
- 写 $0 不产生实际修改；该情况允许 RegWrite 为 0 或写地址为 0 的无效写。**其他条件不成立而明确“不写寄存器”的情况，RegWrite 必须为 0，不能用写回旧值代替。**
- 每条测试指令只使用本册列出的合法编码。不要求处理非法指令和地址异常。未启用写入时，RegData/RegAddr、MemData 等无效总线不要求固定为 0。

## 练习顺序和译码速查

建议先做 E01～E09，再做 E12～E15 和 E18～E20，最后做 E10、E11、E16、E17、E21、E22。E23～E25 可作跳转和字节加载补充。每次只选已完成的题号评测。

熟悉各题后，可以按三道题一组练习。它们只模拟往年题型组合，编码和细节仍以本册为准：

| 组合 | 三道题 | 对应题型来源 |
|---|---|---|
| A | E12 balr、E05 wsbh、E20 lbi | 2020 |
| B | E14 bezal、E09 slo、E19 lwor | 2021 |
| C | E10 qaq、E15 booez、E18 csws | 2023 |
| D | E16 cwp、E17 bgc、E21 lwso | 2024 |

累计实现时，需要同步扩展 type、MUX 选择端、分线器及对应常量的位宽。type 是内部控制编码，可以复用运算功能，不要求每条指令都分配一个独立 ALU 运算编号。

| 题号 | 指令 | 练习内容 | OP（高6位） | FUN（低6位） | 额外固定字段 |
|---|---|---|---|---|---|
'''
    rows=[];sections=[];manifest=[]
    for d in D.values():
        op,fun,bits,syntax=fmt(d);fixed='见下方完整格式'
        if d['name']=='bal':fixed='rs=00000，rt=10001（不是读 $17）'
        if d['fun'] is None:fixed=('rs=00000' if d['name']=='balr' else fixed)
        rows.append(f"| {d['id']} | `{d['name']}` | {d['title']} | `{op}` | `{fun}` | {fixed} |")
        cases=[c for c in CASES if c[0]==d['id']]
        example=EXAMPLES[d['name']]
        sections.append(f"\n## {d['id']} {d['title']}：`{d['name']}`\n\n来源题型：{d['origin']}。\n\n汇编写法：`{syntax}`\n\n32 位格式：`{bits}`\n\n功能：{d['definition']}\n\n示例输入：{example[0]}。\n\n示例结果：{example[1]}。\n\n除题面规定的写入和跳转之外，不修改其他寄存器或内存。配套测试：`tests/{d['id']}/`，{len(cases)} 组程序，{sum(c[3] for c in cases)} 个预定执行周期。\n")
        manifest.append({'id':d['id'],'name':d['name'],'title':d['title'],'opcode':op,'funct':None if d['fun'] is None else fun,'format':bits,'syntax':syntax,'definition':d['definition'],'cases':len(cases)})
    end='''
## 题型来源与整理说明

本练习按功能重新表述，并为原记录缺失或不一致之处确定规则：

- [2019 BUAA-Wander](https://www.cnblogs.com/BUAA-Wander/p/11790154.html)：前导一、整数对数、bal、lbu 的题型。flog2(0)=0 为本练习补充。
- [2020 Roife](https://roife.github.io/posts/buaa-co-lab-p3/)：balr、wsbh、lbi。字节交换以 B A D C 为准。
- [2020 Frida_h](https://www.cnblogs.com/Happy-Huan/p/14055025.html)：bltzalr、movz、lbi。bltzalr 的条件链接规则在本册中明确指定；不宣称与缺失的原题细节相同。
- [2021 FlyingLandlord](https://github.com/flyinglandlord/BUAA-CO-2021/blob/master/P3/P3%E8%AF%BE%E4%B8%8A%E6%B5%8B%E8%AF%95.md)：bezal、slo、lwor。slo 的源值统一为 R[rt]，消除回忆稿中的 rs/rd 笔误。
- [2021 P3/P4 记录的公开部分](https://blog.csdn.net/weixin_41892813/article/details/123252658)：gray、ssze、xor、jas。jas 的公开部分不足以确定完整跳转细节，本练习明确采用 J 型目标拼接和完整 PC；tz(0)=32 为本练习补充。
- [2023 灰雾与红](https://blog.csdn.net/i_want_ak_noip/article/details/134129056)：qaq、booez、csws；使用本合集分配的编码。
- [2024 Lazyfish](https://lazyfish-lc.github.io/2024/10/28/BUAA-CO-P3-test/)：cwp、bgc、lwso。来源文章许可为 CC BY-NC-SA 4.0；本合集相关改编文字沿用该许可并保留来源。其余来源的原文版权归原作者；工具源代码为本次独立编写。

2022 年暂未找到可核实的题面，不虚构年份。2019 年出现的 jal 已在你现有 CPU 中练习过，因此没有重复单列。标准热身题用于补齐相同数据通路所需能力。
'''
    (ROOT/'题目册.md').write_text(intro+'\n'.join(rows)+'\n'+''.join(sections)+end,encoding='utf-8')
    (ROOT/'instructions.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'instructions.tsv').write_text('id\tname\ttitle\top\tfun\n'+''.join(f"{d['id']}\t{d['name']}\t{d['title']}\t{d['op']:06b}\t{'-' if d['fun'] is None else format(d['fun'],'06b')}\n" for d in D.values()),encoding='utf-8')
    (ROOT/'cases.tsv').write_text('exercise\tname\tdirectory\tcycles\treset_mode\tcustom_steps\n'+''.join('\t'.join(map(str,c))+'\n' for c in CASES),encoding='utf-8')
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'tests').rglob('*')) if p.is_file()}
    (ROOT/'checksums.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(f'Generated {len(D)} exercises, {len(CASES)} cases, {sum(c[3] for c in CASES)} cycles, seed={SEED}')

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True);build_tests();documents()
