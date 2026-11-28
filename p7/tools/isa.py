"""Small deterministic assembler. The reference model decodes the resulting words."""
MASK=0xffffffff
R_FUN={'add':0x20,'sub':0x22,'and':0x24,'or':0x25,'slt':0x2a,'sltu':0x2b}
MEM_OP={'lb':0x20,'lh':0x21,'lw':0x23,'sb':0x28,'sh':0x29,'sw':0x2b}

class Program:
    def __init__(self):self.pc=0x3000;self.rows={};self.labels={};self.notes={};self.foci=[]
    def org(self,pc):self.pc=pc
    def label(self,name):
        assert name not in self.labels,name
        self.labels[name]=self.pc
    def emit(self,name,*args):
        pc=self.pc;assert pc not in self.rows,hex(pc)
        self.rows[pc]=(name,args);self.pc+=4;return pc
    def nop(self,n=1):
        for _ in range(n):self.emit('nop')
    def li(self,reg,value):
        value&=MASK;self.emit('lui',reg,value>>16);self.emit('ori',reg,reg,value&65535)
    def la(self,reg,label):self.emit('labelhi',reg,label);self.emit('labello',reg,reg,label)
    def jump(self,label):self.emit('beq',0,0,label);self.nop()
    def cp(self,rd,value,reg=19):self.li(reg,value);self.emit('mtc0',reg,rd)
    def monitor(self,rd,value,reg=19):self.li(reg,value);self.emit('monitor',reg,rd)
    def fault_return(self,label):self.la(21,label)
    def focus(self,name,*args):
        pc=self.emit(name,*args);self.foci.append(pc);return pc
    def finish(self):
        self.nop(8);self.label('finish');self.emit('ori',30,0,0xcafe)
        self.label('halt');self.jump('halt')
    def handler(self,q,entry=0x4180,suffix=''):
        self.org(entry);self.label('handler'+suffix)
        self.emit('mfc0',26,13);self.emit('mfc0',27,14)
        self.emit('mfhi',22);self.emit('mflo',23)
        if q in ('Q07','Q08','Q09','Q10','Q11'):
            self.emit('mfc0',24,20 if q=='Q07' else 18)
            self.emit('mfc0',25,21 if q=='Q07' else 19)
        self.emit('andi',24,26,0x7c)
        self.emit('bne',24,0,'sync'+suffix);self.nop()
        self.emit('sb',0,0x7f20,0)
        self.jump('return'+suffix)
        self.label('sync'+suffix);self.emit('mtc0',21,14)
        self.label('return'+suffix)
        if q=='Q05':self.cp(12,0x10000002,24)
        self.emit('eret');self.emit('ori',29,0,0xdead)
    def resolve(self,value):return self.labels[value] if isinstance(value,str) else value
    def encode_one(self,pc,name,a):
        if name=='nop':return 0
        if name=='raw':return a[0]&MASK
        if name=='labelhi':return (15<<26)|(a[0]<<16)|(self.labels[a[1]]>>16)
        if name=='labello':return (13<<26)|(a[1]<<21)|(a[0]<<16)|(self.labels[a[2]]&65535)
        if name=='watchpc':return (15<<26)|(a[0]<<16)|(self.labels[a[1]]&65535)
        if name in R_FUN:
            rd,rs,rt=a;return (rs<<21)|(rt<<16)|(rd<<11)|R_FUN[name]
        if name in ('mult','multu','div','divu','teq'):
            rs,rt=a;return (rs<<21)|(rt<<16)|{'mult':24,'multu':25,'div':26,'divu':27,'teq':52}[name]
        if name in ('mthi','mtlo','jr'):return (a[0]<<21)|{'mthi':17,'mtlo':19,'jr':8}[name]
        if name in ('mfhi','mflo'):return (a[0]<<11)|{'mfhi':16,'mflo':18}[name]
        if name=='lui':return (15<<26)|(a[0]<<16)|(a[1]&65535)
        if name in ('ori','andi','addi'):
            rt,rs,imm=a;return ({'ori':13,'andi':12,'addi':8}[name]<<26)|(rs<<21)|(rt<<16)|(imm&65535)
        if name in MEM_OP:
            rt,off,base=a;return (MEM_OP[name]<<26)|(base<<21)|(rt<<16)|(off&65535)
        if name in ('beq','bne'):
            rs,rt,target=a;off=(self.resolve(target)-pc-4)//4
            assert -32768<=off<=32767
            return ((4 if name=='beq' else 5)<<26)|(rs<<21)|(rt<<16)|(off&65535)
        if name=='jal':return (3<<26)|((self.resolve(a[0])>>2)&0x3ffffff)
        if name in ('mfc0','mtc0','monitor'):
            rt,rd=a
            return ((0x78000000 if name=='monitor' else 0x40800000 if name=='mtc0' else 0x40000000)
                    |(rt<<16)|(rd<<11))
        if name=='eret':return 0x42000018
        if name=='syscall':return 12
        if name=='withdraw':return 0x04000000
        if name=='tltiu':return (1<<26)|(a[0]<<21)|(11<<16)|(a[1]&65535)
        raise ValueError((name,a))
    def words(self):
        out=[0]*4096
        for pc,(name,a) in self.rows.items():
            assert 0x3000<=pc<=0x6ffc and pc%4==0,hex(pc)
            out[(pc-0x3000)//4]=self.encode_one(pc,name,a)
        return out
    def listing(self):
        words=self.words();out=['# 地址      机器码    汇编；labelhi/labello 分别为 lui/ori 地址装载']
        labels={}
        for k,v in self.labels.items():labels.setdefault(v,[]).append(k)
        for pc,(name,a) in sorted(self.rows.items()):
            for label in labels.get(pc,[]):out.append(label+':')
            out.append(f'{pc:08x}  {words[(pc-0x3000)//4]:08x}  {name} '+', '.join(str(v) for v in a))
        return '\n'.join(out)+'\n'
