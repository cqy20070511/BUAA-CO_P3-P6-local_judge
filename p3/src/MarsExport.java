import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import mars.*;
import mars.mips.hardware.*;
import mars.mips.instructions.*;

/** MARS assembly only. Custom instructions explicitly cannot be simulated by this adapter. */
@SuppressWarnings({"rawtypes","unchecked"})
public final class MarsExport {
    static final class PracticeInstruction extends BasicInstruction {
        PracticeInstruction(String pattern,String description,BasicInstructionFormat format,String mask,SimulationCode code){super(pattern,description,format,mask,code);}
        void prepare(){createExampleTokenList();}
    }
    static void install(Path root)throws Exception {
        Set<String> names=new HashSet<>(Arrays.asList(PracticeRunner.CUSTOM));
        ArrayList instructions=Globals.instructionSet.getInstructionList();
        for(Iterator i=instructions.iterator();i.hasNext();)if(names.contains(((Instruction)i.next()).getName()))i.remove();
        SimulationCode unavailable=statement->{throw new UnsupportedOperationException("This adapter exports machine code only. Use PracticeRunner for execution.");};
        for(String[] d:PracticeRunner.tsv(root.resolve("instructions.tsv"))){
            String n=d[1],op=d[3],fun=d[4],pattern,mask;BasicInstructionFormat format=BasicInstructionFormat.R_FORMAT;
            if(Arrays.asList("xor","sltu","movz","qaq","ssze").contains(n)){
                pattern=n+" $1,$2,$3";mask=op+" sssss ttttt fffff 00000 "+fun;
            }else if(n.equals("srl")||n.equals("slo")){
                pattern=n+" $1,$2,10";mask=op+" 00000 sssss fffff ttttt "+fun;
            }else if(Arrays.asList("wsbh","gray","clo","flog2").contains(n)){
                pattern=n+" $1,$2";mask=n.equals("wsbh")?op+" 00000 sssss fffff 00000 "+fun:op+" sssss 00000 fffff 00000 "+fun;
            }else if(n.equals("bezal")){
                pattern=n+" $1,$2";mask=op+" fffff sssss 00000 00000 "+fun;
            }else if(n.equals("jas")){
                pattern=n+" label";mask=op+" ffffffffffffffffffffffffff";format=BasicInstructionFormat.J_FORMAT;
            }else if(n.equals("bal")){
                pattern=n+" label";mask=op+" 00000 10001 ffffffffffffffff";format=BasicInstructionFormat.I_BRANCH_FORMAT;
            }else if(n.equals("balr")){
                pattern=n+" $1,label";mask=op+" 00000 fffff ssssssssssssssss";format=BasicInstructionFormat.I_BRANCH_FORMAT;
            }else if(Arrays.asList("bltzalr","booez","bgc","cwp").contains(n)){
                pattern=n+" $1,$2,"+(n.equals("cwp")?"100":"label");mask=op+" fffff sssss tttttttttttttttt";
                format=n.equals("cwp")?BasicInstructionFormat.I_FORMAT:BasicInstructionFormat.I_BRANCH_FORMAT;
            }else{
                pattern=n+" $1,-100($2)";mask=op+" ttttt fffff ssssssssssssssss";format=BasicInstructionFormat.I_FORMAT;
            }
            instructions.add(new PracticeInstruction(pattern,"P3 practice "+d[0],format,mask,unavailable));
        }
        for(Object instruction:instructions)if(instruction instanceof PracticeInstruction)((PracticeInstruction)instruction).prepare();
    }
    static Assembler.Program assemble(Path source)throws Exception {
        MemoryConfigurations.setCurrentConfiguration(MemoryConfigurations.getConfigurationByName("CompactDataAtZero"));Globals.memory.clear();
        MIPSprogram mp=new MIPSprogram();Globals.program=mp;ArrayList<String> paths=new ArrayList<>();paths.add(source.toString());
        try{mp.assemble(mp.prepareFilesForAssembly(paths,source.toString(),null),false,true);}
        catch(ProcessingException e){throw new IOException(e.errors().generateErrorAndWarningReport());}
        List statements=mp.getMachineList();int[] words=new int[statements.size()];String[] lines=new String[words.length];
        for(int i=0;i<words.length;i++){ProgramStatement s=(ProgramStatement)statements.get(i);if(s.getAddress()!=0x3000+4*i)throw new IOException("Unexpected text address");words[i]=s.getBinaryStatement();lines[i]=PracticeRunner.name(words[i]);}
        return new Assembler.Program(source.getFileName().toString(),new String(Files.readAllBytes(source),StandardCharsets.UTF_8),words,lines);
    }
    public static void main(String[] args){
        System.setProperty("java.awt.headless","true");System.setProperty("java.util.prefs.PreferencesFactory","MemoryPreferencesFactory");int exit=0;
        try{
            Path root=Paths.get(args[0]).toAbsolutePath();Globals.initialize(false);Globals.getSettings().setBooleanSettingNonPersistent(Settings.DELAYED_BRANCHING_ENABLED,false);install(root);
            if(args.length==1){int count=0;for(String[] c:PracticeRunner.tsv(root.resolve("cases.tsv"))){Path dir=root.resolve(c[2]);Assembler.Program mars=assemble(dir.resolve("program.asm")),raw=Assembler.read(dir.resolve("program.hex"));if(!Arrays.equals(mars.words,raw.words))throw new IOException("MARS/Python machine mismatch: "+c[2]);count++;}System.out.println("MARS ASSEMBLY PASS: "+count+" programs.");}
            else {Assembler.Program p=assemble(Paths.get(args[1]).toAbsolutePath());StringBuilder image=new StringBuilder("v2.0 raw\n");for(int w:p.words)image.append(String.format("%08x%n",w));Path target=Paths.get(args[2]).toAbsolutePath();P3Judge.write(target,image.toString());System.out.println("Exported "+p.words.length+" words: "+target);}
        }catch(Throwable e){e.printStackTrace();exit=2;}
        System.exit(exit);
    }
}
