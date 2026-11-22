import java.nio.file.*;
import java.util.*;
import mars.*;
import mars.mips.hardware.*;
import mars.mips.instructions.BasicInstruction;

/** Real MARS assembler and instruction implementations, executed before the DUT. */
final class MarsOracle {
    static final class Step {
        final P3Judge.Expected e;
        final int[] regs;
        Step(P3Judge.Expected e,int[] r){this.e=e;regs=r;}
    }
    static List<Step> prepare(Assembler.Program p,Path dir,int limit)throws Exception {
        Globals.initialize(false);
        Globals.getSettings().setBooleanSettingNonPersistent(Settings.DELAYED_BRANCHING_ENABLED,false);
        MemoryConfiguration compact=MemoryConfigurations.getConfigurationByName("CompactDataAtZero");
        // Course IM is 4096 words; the stock compact MARS text region is only 1024.
        int[] v=compact.getConfigurationItemValues().clone();
        v[8]=0x6fff;v[9]=0x80000000;v[10]=0x80000000;v[11]=0x80000180;
        v[12]=0x90000000;v[13]=0xffff0000;v[14]=0xffffffff;v[16]=0x7000;
        v[17]=0xfffeffff;v[18]=0x8ffffffc;v[20]=0xffffffff;
        MemoryConfigurations.setCurrentConfiguration(new MemoryConfiguration("P3_4096","P3 extended text",compact.getConfigurationItemNames(),v));
        Globals.memory.clear();
        // Canonical labels make numeric beq offsets unambiguous in MARS.
        StringBuilder source=new StringBuilder(".text 0x3000\n");
        for(int i=0;i<p.words.length;i++) {
            int w=p.words[i];String line=Assembler.disasm(w);
            if((w>>>26)==4) {
                int target=i+1+(short)w;
                if(target<0||target>p.words.length)throw new P3Judge.TestError("beq target outside program at "+Integer.toHexString(0x3000+4*i));
                line=String.format("beq $%d, $%d, P3_%d",(w>>>21)&31,(w>>>16)&31,target);
            }
            source.append("P3_").append(i).append(": ").append(line).append('\n');
        }
        source.append("P3_").append(p.words.length).append(":\n");
        Path input=dir.resolve("mars_normalized.asm");P3Judge.write(input,source.toString());
        MIPSprogram mp=new MIPSprogram();Globals.program=mp;
        ArrayList<String> files=new ArrayList<>();files.add(input.toString());
        try {mp.assemble(mp.prepareFilesForAssembly(files,input.toString(),null),false,true);}
        catch(ProcessingException ex){throw new P3Judge.TestError("MARS 汇编失败："+ex.errors().generateErrorAndWarningReport());}
        if(mp.getMachineList().size()!=p.words.length)throw new P3Judge.TestError("MARS instruction count differs; pseudo expansion is not allowed");
        StringBuilder machine=new StringBuilder();
        for(int i=0;i<p.words.length;i++) {
            ProgramStatement st=(ProgramStatement)mp.getMachineList().get(i);
            if(st.getBinaryStatement()!=p.words[i]||st.getAddress()!=0x3000+4*i)throw new P3Judge.TestError("MARS machine code disagrees at instruction "+i);
            machine.append(String.format("%08x%n",st.getBinaryStatement()));
        }
        P3Judge.write(dir.resolve("mars_machine.txt"),machine.toString());
        Globals.program=new MIPSprogram(); // disable undo recording during synchronous stepping
        RegisterFile.resetRegisters();for(int i=1;i<32;i++)RegisterFile.updateRegister(i,0);
        RegisterFile.initializeProgramCounter(0x3000);
        P3Judge.Reference ref=new P3Judge.Reference();List<Step> steps=new ArrayList<>();
        for(int cycle=0;cycle<limit;cycle++) {
            if((cycle&63)==0&&P3Judge.config!=null)P3Judge.budget();
            int pc=RegisterFile.getProgramCounter(),i=(pc-0x3000)/4;
            if((pc&3)!=0||i<0||i>=p.words.length)throw new P3Judge.TestError("参考程序跳出已定义指令 @"+Integer.toHexString(pc));
            int w=p.words[i];P3Judge.Expected e=ref.decode(w);
            // P3 defines wrapping add/sub. Only reference execution uses the unsigned forms.
            int mw=w;if((w>>>26)==0&&((w&63)==32||(w&63)==34))mw=w+1;
            // Preserve the assembler's signed load/store operands. MARS's binary-only
            // constructor does not sign-extend those operands in version 4.5.
            ProgramStatement st=mw==w?(ProgramStatement)mp.getMachineList().get(i):new ProgramStatement(mw,pc);
            RegisterFile.incrementPC();
            try {((BasicInstruction)st.getInstruction()).getSimulationCode().simulate(st);}
            catch(ProcessingException ex){throw new P3Judge.TestError("MARS 执行错误 @"+Integer.toHexString(pc)+": "+ex.errors().generateErrorAndWarningReport());}
            ref.commit(e);
            if(RegisterFile.getProgramCounter()!=ref.pc)throw new P3Judge.TestError("参考模型与 MARS 的 PC 不一致");
            int[] regs=new int[32];for(int r=0;r<32;r++){regs[r]=RegisterFile.getValue(r);if(regs[r]!=ref.regs[r])throw new P3Judge.TestError("参考模型与 MARS 寄存器不一致");}
            for(int a=0;a<3072;a++)if(Globals.memory.getWord(a*4)!=ref.memory[a])throw new P3Judge.TestError("参考模型与 MARS 内存不一致："+a*4);
            if(e.writesReg)e.regData=regs[e.reg]; // $0 has no architecturally visible write data
            steps.add(new Step(e,regs));
            if(ref.pc==0x3000+4*p.words.length||(i==p.words.length-1&&e.branchTaken&&e.next==e.pc))return steps;
        }
        throw new P3Judge.TestError("MARS 参考程序超过周期上限 "+limit+"；请在末尾使用 beq $0,$0,标签，或自然结束。");
    }
}
