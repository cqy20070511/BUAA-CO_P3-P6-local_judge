import java.util.*;

public final class TestSuite {
    public static final class Case {
        public final String name,purpose;
        public final Assembler.Program program,warmup;
        public Case(String n,String p,String s){this(n,p,Assembler.assemble(n,s),null);}
        public Case(String n,String p,Assembler.Program s,Assembler.Program w){name=n;purpose=p;program=s;warmup=w;}
    }
    static final class B {
        final StringBuilder s=new StringBuilder(".text 0x3000\n");
        B emit(String f,Object...v){s.append(String.format(Locale.ROOT,f,v)).append('\n');return this;}
        B li(int r,int value){return emit("lui $%d, 0x%04x",r,value>>>16).emit("ori $%d, $%d, 0x%04x",r,r,value&65535);}
        String end(){return s.toString()+"finish: beq $0, $0, finish\n";}
    }
    public static List<Case> create(int randomCases,long seed,boolean fullMemory) {
        List<Case> out=new ArrayList<>();B b;
        out.add(new Case("01_pc_advance","First instruction and the following PC/ROM words; detects repeated @3000",new B().emit("ori $8, $0, 4").emit("lui $9, 0x873d").emit("ori $9, $9, 0x1234").end()));
        out.add(new Case("02_feedback_prefixes","Regression: the four failing prefixes from the submitted screenshot",new B().li(28,0x9a7c66ae).li(1,0x12320000).li(2,0x31230000).li(5,0x12344321).end()));
        b=new B();for(int n=1;n<32;n++)b.li(n,0x10203040+n*0x01010101);for(int n=0;n<32;n++)b.emit("sw $%d, %d($0)",n,n*4);
        out.add(new Case("03_registers","All 32 register indices and reads; nonzero initialization",b.end()));
        b=new B();b.li(1,0x11223344).li(2,0x55667788);
        b.emit("add $0, $1, $2").emit("sw $0, 0($0)").emit("sub $0, $1, $2").emit("ori $0, $0, 65535").emit("lui $0, 65535");
        b.emit("sw $1, 4($0)").emit("lw $0, 4($0)").emit("add $3, $0, $1").emit("sw $0, 8($0)").emit("sw $3, 12($0)");
        out.add(new Case("04_zero_register","Attempted writes to $0 must not affect subsequent operands or memory",b.end()));
        int[] edges={0,1,-1,2,-2,0x7fffffff,0x80000000,0x7ffffffe,0x80000001};
        b=new B();int z=0;for(int a:edges)for(int c:edges){b.li(1,a).li(2,c).emit("add $3, $1, $2").emit("sub $4, $1, $2");if(z++%5==0)b.emit("add $1, $1, $2").emit("sub $2, $1, $2");}
        out.add(new Case("05_arithmetic_edges","Modulo-2^32 addition/subtraction, both operands, and aliased destinations",b.end()));
        b=new B();int[] imms={0,1,2,3,0x20,0x22,0x7fff,0x8000,0xfffd,0xfffe,0xffff,25779,42528};
        for(int a:new int[]{0,-1,0x12345678,0x80000000,0x0000ffff})for(int imm:imms)b.li(1,a).emit("ori $2, $1, %d",imm).emit("ori $1, $1, %d",imm);
        out.add(new Case("06_ori","OR versus XOR; zero extension; immediate low bits equal to R funct codes",b.end()));
        b=new B();for(int n=0;n<32;n++)b.emit("lui $%d, %d",n,imms[n%imms.length]);for(int n=0;n<32;n++)b.emit("sw $%d, %d($0)",n,n*4);
        out.add(new Case("07_lui","LUI upper/lower halves, all destination indices, immediate boundaries",b.end()));
        b=new B();b.li(1,0x89abcdef);int[] addrs={0,4,8,0x3fc,0x400,0xffc,0x1000,0x1ffc,0x2000,0x2ff8,0x2ffc};
        for(int a:addrs)b.emit("sw $1, %d($0)",a).emit("lw $2, %d($0)",a).emit("ori $1, $1, 1");
        out.add(new Case("08_memory_boundaries","Aligned accesses across the complete legal DM range; nonzero bytes",b.end()));
        b=new B();b.li(1,0xa1b2c3d4).li(8,0x8000).emit("sw $1, -32768($8)").emit("lw $2, -32768($8)");
        b.li(8,-32767).emit("sw $1, 32767($8)").emit("lw $3, 32767($8)");
        b.li(8,-4).emit("sw $1, 4($8)").emit("lw $4, 4($8)");
        b.li(8,0x3000).emit("sw $1, -4($8)").emit("lw $5, -4($8)");
        b.li(8,4).emit("sw $1, -4($8)").emit("lw $6, -4($8)");
        out.add(new Case("09_signed_offsets","Negative and extreme offsets; negative base plus positive offset; legal effective addresses",b.end()));
        b=new B();b.li(1,0x13579bdf).emit("sw $1, 0($0)").emit("lw $1, 0($0)").emit("sw $1, 4($0)").emit("lw $2, 4($0)").emit("add $2, $2, $1").emit("sw $2, 0($0)").emit("lw $3, 0($0)");
        out.add(new Case("10_dependencies","Immediate load-use, store-load, same-register dependencies, and overwrite",b.end()));
        b=new B();b.li(1,0x12345678).li(2,0x12345678).li(3,0x12345679);
        b.emit("beq $1, $2, equal").emit("ori $4, $0, 0xdead").emit("equal: ori $4, $0, 0xbeef");
        b.emit("beq $1, $3, unequal_skip").emit("ori $5, $0, 0x2468").emit("unequal_skip: nop");
        b.emit("beq $1, $2, 0").emit("ori $6, $0, 0x1111").emit("beq $1, $3, -1").emit("ori $7, $0, 0x2222");
        out.add(new Case("11_branch_forward","Taken/non-taken forward branches, zero offset, non-taken self branch; no delay slots",b.end()));
        b=new B();b.emit("ori $1, $0, 7").emit("ori $2, $0, 1").emit("loop: sub $1, $1, $2").emit("beq $1, $0, done").emit("beq $0, $0, loop").emit("done: sw $1, 0($0)");
        out.add(new Case("12_branch_backward","Negative branch offset and a finite countdown loop",b.end()));
        b=new B();z=0;for(int a:edges)for(int c:edges){String l="branch_"+(z++);b.li(1,a).li(2,c).emit("beq $1, $2, %s",l).emit("ori $3, $0, 1").emit(l+": ori $4, $0, 2");}
        out.add(new Case("13_branch_comparison","Equality around signed/unsigned 32-bit boundaries",b.end()));
        b=new B();for(int n=0;n<20;n++)b.emit("nop");b.emit("ori $1, $0, 0x20").emit("nop").emit("ori $2, $1, 0x22").emit("nop");
        out.add(new Case("14_nop","NOPs advance PC without meaningful writes",b.end()));
        b=new B();b.emit("beq $0, $0, last_word");for(int n=1;n<4095;n++)b.emit("nop");b.emit("last_word: ori $31, $0, 65535");
        out.add(new Case("15_im_last_word","ROM[4095] maps to PC=0x6ffc; 4096-word capacity",b.s.toString()));
        B warm=new B();for(int n=1;n<32;n++)warm.li(n,0x89abcdef^n);
        for(int a:addrs)warm.emit("sw $1, %d($0)",a);
        b=new B();for(int n=0;n<32;n++)b.emit("sw $%d, %d($0)",n,0x800+n*4);
        for(int a:addrs)b.emit("lw $2, %d($0)",a);
        out.add(new Case("16_async_reset","Reset PC/GRF/DM after active execution, without a new clock edge",Assembler.assemble("reset_check",b.end()),Assembler.assemble("reset_warmup",warm.end())));
        addTutorialCases(out);
        for(int n=0;n<randomCases;n++)out.add(random(n,seed));
        if(fullMemory) {
            b=new B();b.emit("ori $8, $0, 0").emit("ori $9, $0, 0x3000").emit("ori $10, $0, 4").li(11,0x89abcdef);
            b.emit("store_loop: sw $11, 0($8)").emit("add $11, $11, $10").emit("add $8, $8, $10").emit("beq $8, $9, load_start").emit("beq $0, $0, store_loop");
            b.emit("load_start: ori $8, $0, 0").emit("load_loop: lw $12, 0($8)").emit("add $8, $8, $10").emit("beq $8, $9, finish").emit("beq $0, $0, load_loop");
            out.add(new Case("full_dm_sweep","All 3072 words hold DISTINCT nonzero-byte values before reading; detects address aliasing",b.end()));
            B fill=new B();fill.emit("ori $8, $0, 0").emit("ori $9, $0, 0x3000").emit("ori $10, $0, 4").li(11,0x89abcdef);
            fill.emit("fill: sw $11, 0($8)").emit("add $11, $11, $10").emit("add $8, $8, $10").emit("beq $8, $9, finish").emit("beq $0, $0, fill");
            B check=new B();check.emit("ori $8, $0, 0").emit("ori $9, $0, 0x3000").emit("ori $10, $0, 4");
            check.emit("check: lw $12, 0($8)").emit("add $8, $8, $10").emit("beq $8, $9, finish").emit("beq $0, $0, check");
            out.add(new Case("full_dm_async_reset","Fill all 3072 words, asynchronously reset, then check every word is zero",Assembler.assemble("reset_all",check.end()),Assembler.assemble("fill_all",fill.end())));
        }
        return out;
    }
    static void addTutorialCases(List<Case> out) {
        int[] data={-2,-1,0,1,2,0x80000000,0x80000001,0x7ffffffe,0x7fffffff,-1000786109,1919156834};
        B b=new B();for(int a:data)for(int c:data)b.li(1,a).li(2,c).emit("add $3, $1, $2").emit("sub $4, $1, $2");
        out.add(new Case("17_tutorial_data","Exact tutorial values; Cartesian product of both add/sub operands",b.end()));
        b=new B();b.emit("ori $1, $0, 1").emit("ori $2, $0, 2");
        b.emit("before: ori $3, $0, 3").emit("beq $1, $2, before");
        b.emit("self_nt: beq $1, $2, self_nt").emit("beq $1, $2, forward_nt").emit("ori $4, $0, 0x4444");
        b.emit("forward_nt: beq $1, $1, forward_yes").emit("ori $5, $0, 0xdead");
        b.emit("forward_yes: ori $6, $0, 2").emit("ori $7, $0, 1");
        b.emit("back: sub $6, $6, $7").emit("beq $6, $0, after_back").emit("beq $0, $0, back");
        b.emit("after_back: sw $4, 0($0)");
        out.add(new Case("18_six_branch_modes","Taken/not-taken x target before/self/after; each case is executed",b.end()));
        int[] offsets={-32768,-32767,-5329,-2,-1,0,1,2,3,4,25299,32766,32767};
        int[] addrs={0,4,0x3fc,0x400,0x7fc,0x800,0xffc,0x1000,0x1ffc,0x2000,0x2ffc};
        for(int part=0;part<2;part++) {
            b=new B();int k=0;
            for(int n=part;n<offsets.length;n+=2)for(int a:addrs){int off=offsets[n],v=0x11223345+(k++)*0x01010104;
                b.li(1,v|0x01010101).li(8,a-off).emit("sw $1, %d($8)",off).emit("lw $2, %d($8)",off);
            }
            out.add(new Case("19_offset_matrix_"+part,"Extreme signed offsets and mixed positive/negative bases; all effective addresses legal",b.end()));
        }
        b=new B();for(int n=1;n<32;n++)b.li(n,0x01010101*n);
        for(int a=0;a<32;a++)for(int c=0;c<32;c++) {
            // Split into <=1024-word cases so MARS can also assemble each test.
            if(a%8==0&&c==0&&a!=0){out.add(new Case("20_register_pairs_"+(a/8-1),"All rs/rt combinations, including source/destination aliasing",b.end()));b=new B();for(int n=1;n<32;n++)b.li(n,0x01010101*n);}
            b.emit("add $%d, $%d, $%d",a,a,c).emit("sub $%d, $%d, $%d",c,a,c);
        }
        out.add(new Case("20_register_pairs_3","All rs/rt combinations, including source/destination aliasing",b.end()));
        b=new B();for(int n=0;n<32;n++)b.li(n,0x01010101*n);
        for(int n=0;n<32;n++)b.emit("lui $%d, 0x8000",n).emit("ori $%d, $%d, 65535",n,n).emit("sw $%d, %d($0)",n,n*4);
        out.add(new Case("21_lui_overwrite","LUI must clear previously nonzero low halves; all destinations",b.end()));
    }
    static Case random(int index,long seed) {
        Random r=new Random(seed+0x9e3779b97f4a7c15L*(index+1));B b=new B();
        for(int n=1;n<32;n++)b.li(n,r.nextInt());
        for(int n=0;n<300;n++) {
            int a=r.nextInt(32),c=r.nextInt(32),d=r.nextInt(32),kind=r.nextInt(9);
            if(kind==0)b.emit("add $%d, $%d, $%d",d,a,c);
            else if(kind==1)b.emit("sub $%d, $%d, $%d",d,a,c);
            else if(kind==2)b.emit("ori $%d, $%d, %d",c,a,r.nextInt(65536));
            else if(kind==3)b.emit("lui $%d, %d",c,r.nextInt(65536));
            else if(kind==4||kind==5){int addr=r.nextInt(3072)*4;int offset=r.nextInt(65536)-32768;int base=addr-offset;
                b.li(30,base).emit("%s $%d, %d($30)",kind==4?"sw":"lw",c,offset);
            } else if(kind==6||kind==7)b.emit("beq $%d, $%d, rand_%d",a,kind==6?a:c,n).emit("ori $%d, $0, %d",d,r.nextInt(65536)).emit("rand_%d: nop",n);
            else b.emit("nop");
        }
        return new Case(String.format("random_%03d",index+1),"Deterministic random mix; seed="+seed+", index="+index,b.end());
    }
}
