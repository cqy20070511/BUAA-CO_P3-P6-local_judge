import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

/** Executes real Logisim circuits; Python test expectations are audited by an independent Java model. */
public final class PracticeRunner {
    static final String[] CUSTOM={"xor","srl","sltu","movz","wsbh","gray","clo","flog2","slo","qaq","ssze","balr","bltzalr","bezal","booez","cwp","bgc","csws","lwor","lbi","lwso","jas","bal","lbu","lb"};
    static Path root,out,cpu;static P3Judge.Simulator sim;static StorageLayout layout;
    static int passed,failed,errors,totalCycles,sample;static boolean auditOnly;
    static final List<String[]> results=new ArrayList<>();
    static String hex(int v){return String.format("%08x",v);}
    static int x(String s){return (int)Long.parseLong(s,16);}
    static String sha(byte[] b)throws Exception {byte[] h=MessageDigest.getInstance("SHA-256").digest(b);StringBuilder s=new StringBuilder();for(byte v:h)s.append(String.format("%02x",v&255));return s.toString();}
    static String digest(int[] values)throws Exception {ByteBuffer b=ByteBuffer.allocate(4*values.length).order(ByteOrder.LITTLE_ENDIAN);for(int v:values)b.putInt(v);return sha(b.array());}
    static List<String[]> tsv(Path p)throws Exception {List<String[]> a=new ArrayList<>();for(String s:Files.readAllLines(p,StandardCharsets.UTF_8))if(!s.trim().isEmpty())a.add(s.split("\t",-1));if(a.isEmpty())throw new IOException("Empty table: "+p);a.remove(0);return a;}
    static String name(int w)throws Exception {
        if(w==0)return "nop";int op=w>>>26,f=w&63;
        if(op==0){switch(f){case 32:return "add";case 34:return "sub";case 38:return "xor";case 2:return "srl";case 43:return "sltu";case 10:return "movz";case 44:return "wsbh";case 45:return "gray";case 48:return "clo";case 49:return "flog2";case 50:return "slo";case 51:return "qaq";case 52:return "ssze";case 53:return "bezal";}}
        switch(op){case 13:return "ori";case 15:return "lui";case 35:return "lw";case 43:return "sw";case 4:return "beq";case 48:return "balr";case 49:return "bltzalr";case 50:return "booez";case 51:return "cwp";case 52:return "bgc";case 53:return "csws";case 54:return "lwor";case 55:return "lbi";case 56:return "lwso";case 57:return "jas";case 1:return "bal";case 36:return "lbu";case 32:return "lb";}
        throw new IllegalArgumentException("Unrecognized word "+hex(w));
    }
    static P3Judge.Expected decode(P3Judge.Reference s,int w)throws Exception {
        P3Judge.Expected e=new P3Judge.Expected();e.pc=s.pc;e.word=w;e.next=s.pc+4;e.instruction=name(w);
        int rs=w>>>21&31,rt=w>>>16&31,rd=w>>>11&31,sh=w>>>6&31,imm=(short)w,u=w&65535,a=s.regs[rs],b=s.regs[rt];e.reg=rt;
        String n=e.instruction;
        switch(n){
            case "nop":break;
            case "add":case "sub":case "xor":case "sltu":case "movz":case "qaq":case "ssze":
                e.writesReg=true;e.reg=rd;
                if(n.equals("add"))e.regData=a+b;
                if(n.equals("sub"))e.regData=a-b;
                if(n.equals("xor"))e.regData=a^b;
                if(n.equals("sltu"))e.regData=Integer.compareUnsigned(a,b)<0?1:0;
                if(n.equals("movz")){e.writesReg=b==0;e.regData=a;}
                if(n.equals("qaq"))e.regData=(int)((long)a*a)&(int)((long)b*b);
                if(n.equals("ssze"))e.regData=Integer.numberOfTrailingZeros(a)==Integer.numberOfTrailingZeros(b)?1:a-b;
                break;
            case "srl":case "slo":e.writesReg=true;e.reg=rd;e.regData=n.equals("srl")?b>>>sh:(b<<sh)|(int)((1L<<sh)-1);break;
            case "wsbh":e.writesReg=true;e.reg=rd;e.regData=((b>>>8)&0x00ff00ff)|((b<<8)&0xff00ff00);break;
            case "gray":e.writesReg=true;e.reg=rd;e.regData=a^(a>>>1);break;
            case "clo":e.writesReg=true;e.reg=rd;e.regData=Integer.numberOfLeadingZeros(~a);break;
            case "flog2":e.writesReg=true;e.reg=rd;e.regData=a==0?0:31-Integer.numberOfLeadingZeros(a);break;
            case "ori":e.writesReg=true;e.regData=a|u;break;
            case "lui":e.writesReg=true;e.regData=u<<16;break;
            case "beq":case "booez":case "bgc":case "bal":case "balr":case "bltzalr":
                boolean take=n.equals("bal")||n.equals("balr");
                if(n.equals("beq"))take=a==b;
                if(n.equals("booez"))take=(Integer.bitCount(a&65535)&1)==1&&(Integer.bitCount((~b)>>>16)&1)==0;
                if(n.equals("bgc")){int count=0;for(int k=0;k<32;k+=2){int pair=(a>>>k)&3;count+=Integer.bitCount(pair^(pair>>>1));}take=count>rt;}
                if(n.equals("bltzalr"))take=a<0;
                if(take)e.next=s.pc+4+(imm<<2);
                if(take&&(n.equals("bal")||n.equals("balr")||n.equals("bltzalr"))){e.writesReg=true;e.reg=n.equals("bal")?31:rt;e.regData=s.pc+4;}
                break;
            case "bezal":if(b==0){e.writesReg=true;e.reg=31;e.regData=s.pc+4;e.next=a;}break;
            case "cwp":e.writesReg=true;e.reg=Integer.compareUnsigned(u<<8,s.pc)>0?rs:rt;e.regData=u;break;
            default:
                e.memAddr=n.equals("jas")?s.regs[29]:a+imm;
                if(n.equals("lwor"))e.memAddr=(e.memAddr+4*rt)&0x7c;
                if(Integer.compareUnsigned(e.memAddr,0x2fff)>0||(!Arrays.asList("lbi","lbu","lb").contains(n)&&(e.memAddr&3)!=0))throw new IOException("Reference invalid EA "+hex(e.memAddr));
                int word=s.memory[e.memAddr>>>2];
                if(n.equals("sw")||n.equals("csws")||n.equals("jas")){
                    e.writesMem=true;e.memData=n.equals("jas")?s.pc+4:n.equals("csws")&&b>=0?0:b;
                    if(n.equals("jas"))e.next=((s.pc+4)&0xf0000000)|((w&0x3ffffff)<<2);
                }else{
                    e.loads=true;e.writesReg=true;e.regData=word;
                    if(n.equals("lbi")){int mask=255<<((e.memAddr&3)*8);e.regData=(b&~mask)|(word&mask);}
                    if(n.equals("lbu")||n.equals("lb")){int byteValue=(word>>>((e.memAddr&3)*8))&255;e.regData=n.equals("lb")?(int)(byte)byteValue:byteValue;}
                    if(n.equals("lwso")){int h=b&15;e.reg=(word&1)!=0?(b<<h)&31:(b>>>h)&31;}
                }
        }
        return e;
    }
    static P3Judge.Expected expected(String[] row){
        P3Judge.Expected e=new P3Judge.Expected();e.pc=x(row[1]);e.word=x(row[2]);e.next=x(row[3]);e.writesReg=row[4].equals("1");e.reg=Integer.parseInt(row[5]);e.regData=x(row[6]);e.writesMem=row[7].equals("1");e.memAddr=x(row[8]);e.memData=x(row[9]);e.loads=row[10].equals("1");e.instruction=row[11];return e;
    }
    static void equivalent(P3Judge.Expected a,P3Judge.Expected b)throws Exception {
        boolean ok=a.pc==b.pc&&a.word==b.word&&a.next==b.next&&a.writesReg==b.writesReg&&a.writesMem==b.writesMem&&a.loads==b.loads&&a.instruction.equals(b.instruction);
        if(a.writesReg)ok&=a.reg==b.reg&&a.regData==b.regData;
        if(a.loads||a.writesMem)ok&=a.memAddr==b.memAddr;
        if(a.writesMem)ok&=a.memData==b.memData;
        if(!ok)throw new IOException("Python/Java reference mismatch @"+hex(a.pc)+" "+a.instruction);
    }
    static List<P3Judge.Expected> audit(Assembler.Program p,List<String[]> rows)throws Exception {
        P3Judge.Reference r=new P3Judge.Reference();List<P3Judge.Expected> steps=new ArrayList<>();int i=0;
        for(String[] row:rows){
            if(Integer.parseInt(row[0])!=i++)throw new IOException("Trace cycle numbering");
            int index=(r.pc-0x3000)/4;if((r.pc&3)!=0||index<0||index>=p.words.length)throw new IOException("Trace PC outside program");
            P3Judge.Expected e=expected(row),j=decode(r,p.words[index]);equivalent(e,j);r.commit(j);
            if(!digest(r.regs).equals(row[12])||!digest(r.memory).equals(row[13]))throw new IOException("State digest mismatch after "+e.instruction+" @"+hex(e.pc));
            steps.add(e);
        }
        if(steps.isEmpty())throw new IOException("No steps; refusing vacuous PASS");return steps;
    }
    static void check(TraceArchive tr,P3Judge.Reference ref,Assembler.Program p,int cycle,String event,int pc,int word)throws Exception {
        int[][] actual=layout.capture(sim);sample=tr.sample(sim,"test",cycle,event,pc,word,ref,actual,p);
        String mismatch=layout.compare(actual,ref,p,false);
        if(mismatch!=null)throw new P3Judge.Failure("内部状态："+mismatch);
        sim.expect("PC 状态","pc",ref.pc);
    }
    static void resetMatrix(String mode,TraceArchive tr,P3Judge.Reference dirty,Assembler.Program p)throws Exception {
        if(mode.equals("none"))return;
        if(!mode.equals("high")){
            for(int k=0;sim.state.getValue(sim.clock.getLocation()).toIntValue()!=0;k++){
                if(k>10000)throw new IOException("Clock never low");sim.state.getPropagator().tick();sim.settle();
                check(tr,dirty,p,-1,"before_reset_falling",dirty.pc,0);
            }
        }
        sim.setInput("reset",1);sim.settle();P3Judge.Reference zero=new P3Judge.Reference();check(tr,zero,p,-1,"reset_assert_no_edge",0x3000,0);
        if(mode.equals("across_rising")){
            for(int k=0;;k++){if(k>10000)throw new IOException("Clock never rises");sim.state.getPropagator().tick();sim.settle();check(tr,zero,p,-1,"reset_held",0x3000,0);if(sim.state.getValue(sim.clock.getLocation()).toIntValue()==1)break;}
        }
        sim.setInput("reset",0);sim.settle();check(tr,zero,p,-1,"reset_release_no_edge",0x3000,0);
        // Check the first real instruction after reset; reset must not damage the ROM.
        P3Judge.Expected e=decode(zero,p.words[0]);sim.compare(e);sim.rising();zero.commit(e);check(tr,zero,p,0,"restart_post_edge",e.pc,e.word);
    }
    static void run(String[] c,int ordinal,int count)throws Exception {
        String id=c[0],label=c[1];Path source=root.resolve(c[2]),dir=out.resolve(c[2]);Files.createDirectories(dir);
        Assembler.Program p=Assembler.read(source.resolve("program.hex"));List<String[]> rows=tsv(source.resolve("expected.tsv"));
        List<P3Judge.Expected> steps=audit(p,rows);
        if(steps.size()!=Integer.parseInt(c[3]))throw new IOException("Case cycle count mismatch");
        if(auditOnly){passed++;totalCycles+=steps.size();return;}
        for(String file:new String[]{"program.hex","program.asm","listing.txt","expected.tsv"})Files.copy(source.resolve(file),dir.resolve(file),StandardCopyOption.REPLACE_EXISTING);
        String status="PASS",reason="";int cycle=0;P3Judge.Expected active=steps.get(0);sample=0;long start=System.nanoTime();
        try(TraceArchive tr=new TraceArchive(dir,layout)){
            sim.fresh(p);AutomationRunner.sim=sim;AutomationRunner.exportCircuit(cpu,dir.resolve("CPU_loaded.circ"),p);
            P3Judge.Reference ref=new P3Judge.Reference();check(tr,ref,p,0,"initial_reset",ref.pc,p.words[0]);
            for(P3Judge.Expected e:steps){
                active=e;check(tr,ref,p,cycle,"pre_edge",e.pc,e.word);sim.compare(e);
                if(!e.writesReg&&!e.instruction.equals("nop"))sim.expect("本条指令禁止寄存器写入","RegWrite",0);
                sim.rising();ref.commit(e);check(tr,ref,p,cycle,"post_edge",e.pc,e.word);cycle++;totalCycles++;
            }
            resetMatrix(c[4],tr,ref,p);
        }catch(P3Judge.Failure e){status="WA";reason=e.getMessage();}
        catch(Exception e){status="ERROR";reason=e.toString();}
        if(!status.equals("PASS")){
            String message="题号："+id+"\n用例："+label+"\n周期（从0开始）："+cycle+"\nPC："+hex(active.pc)+"\n指令："+active.instruction+"\n机器码："+hex(active.word)+"\n"+reason+"\n预期 nextPC："+hex(active.next)+"\n";
            P3Judge.write(dir.resolve("failure.txt"),message);
            if(sample>0)P3Judge.write(dir.resolve("failure_state.csv"),TraceArchive.read(dir.resolve("state.p3trace.gz"),sample).csv());
            System.out.println(message);
        }
        if(status.equals("PASS"))passed++;else if(status.equals("WA"))failed++;else errors++;
        results.add(new String[]{id,label,status,""+cycle,hex(active.pc),active.instruction,reason,c[2]});
        System.out.println("["+ordinal+"/"+count+"] "+id+" "+status+" "+label+" ("+cycle+" cycles, "+(System.nanoTime()-start)/1000000+" ms)");
    }
    static void report(String fatal,String hash)throws Exception {
        String verdict=fatal.isEmpty()&&failed==0&&errors==0?"PASS":errors>0||!fatal.isEmpty()?"ERROR":"FAIL";
        StringBuilder m=new StringBuilder("# P3 加指令练习评测\n\n结果：**"+verdict+"**\n\n通过 "+passed+"，电路不匹配 "+failed+"，工具/适配错误 "+errors+"；执行 "+totalCycles+" 周期。\n\n电路 SHA-256：`"+hash+"`\n\n原电路只读；测试 ROM 仅写入仿真状态和结果目录中的副本。无延迟槽，链接值 PC+4。每周期检查有效的八个顶层信号以及真实 PC、GRF、DM、IM 状态；无效总线不强制数值，未使用的物理 $0 寄存器不作为架构错误。\n\n");
        if(!fatal.isEmpty())m.append("致命错误：").append(fatal).append("\n\n");
        m.append("| 题号 | 用例 | 状态 | 已执行周期 | 定位 |\n|---|---|---|---|---|\n");
        StringBuilder h=new StringBuilder("<!doctype html><html lang=zh-CN><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>P3练习报告</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}pre{white-space:pre-wrap;background:#f3f5f7;padding:12px}.PASS{color:#167342}.WA,.ERROR{color:#bd2934}</style><h1>P3加指令练习："+verdict+"</h1><p>通过 "+passed+"，不匹配 "+failed+"，错误 "+errors+"；执行 "+totalCycles+" 周期。</p><p>CPU SHA-256: "+hash+"</p><p>状态错误先检查报告中的信号/存储路径。控制器 type 数值不限，只检查行为。</p>");
        if(!fatal.isEmpty())h.append("<pre>").append(P3Judge.h(fatal)).append("</pre>");
        h.append("<table><tr><th>题号</th><th>用例</th><th>结果</th><th>周期</th><th>详情</th></tr>");
        for(String[] r:results){m.append('|').append(r[0]).append('|').append(r[1]).append('|').append(r[2]).append('|').append(r[3]).append('|').append(r[6].replace("\n"," ").replace("|","/")).append("|\n");
            h.append("<tr><td>").append(r[0]).append("</td><td>").append(P3Judge.h(r[1])).append("</td><td class='").append(r[2]).append("'>").append(r[2]).append("</td><td>").append(r[3]).append("</td><td><a href='").append(r[7]).append("/signals.csv'>信号</a> · <a href='").append(r[7]).append("/expected.tsv'>期望</a> · <a href='").append(r[7]).append("/CPU_loaded.circ'>带ROM电路</a>");
            if(!r[2].equals("PASS"))h.append(" · <a href='").append(r[7]).append("/failure.txt'>失败位置</a> · <a href='").append(r[7]).append("/failure_state.csv'>完整失败状态</a><pre>").append(P3Judge.h(r[6])).append("</pre>");h.append("</td></tr>");}
        P3Judge.write(out.resolve("检查报告.md"),m.toString());P3Judge.write(out.resolve("report.html"),h.append("</table></html>").toString());
        try(PrintWriter w=new PrintWriter(Files.newBufferedWriter(out.resolve("results.csv"),StandardCharsets.UTF_8))){P3Judge.csv(w,new String[]{"exercise","case","status","cycles","pc","instruction","reason","directory"});for(String[] r:results)P3Judge.csv(w,r);}
    }
    public static void main(String[] args){
        System.setProperty("java.awt.headless","true");System.setProperty("java.util.prefs.PreferencesFactory","MemoryPreferencesFactory");
        String selected="",rom=null,fatal="",hash="";boolean list=false;int exit=0;byte[] before=null;
        try{
            root=Paths.get(PracticeRunner.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toAbsolutePath().getParent();
            for(int i=0;i<args.length;i++){switch(args[i]){case "--root":root=Paths.get(args[++i]).toAbsolutePath();break;case "--cpu":cpu=Paths.get(args[++i]).toAbsolutePath();break;case "--exercise":selected=args[++i];break;case "--out":out=Paths.get(args[++i]).toAbsolutePath();break;case "--rom":rom=args[++i];break;case "--self-test":auditOnly=true;break;case "--list":list=true;break;default:throw new IllegalArgumentException("Unknown argument: "+args[i]);}}
            List<String[]> instructions=tsv(root.resolve("instructions.tsv"));
            if(list){for(String[] d:instructions)System.out.println(d[0]+" "+d[1]+" "+d[2]+" OP="+d[3]+" FUN="+d[4]);return;}
            Set<String> ids=new HashSet<>();
            if(selected.equalsIgnoreCase("all")||auditOnly&&selected.isEmpty()){ids.add("BASE");for(String[] d:instructions)ids.add(d[0]);}
            else {for(String token:selected.split(",")){String id=token.trim();boolean found=id.equalsIgnoreCase("BASE");if(found)ids.add("BASE");for(String[] d:instructions)if(d[0].equalsIgnoreCase(id)||d[1].equalsIgnoreCase(id)){ids.add(d[0]);found=true;}if(!found)throw new IllegalArgumentException("未知题号/指令："+id+"；请用 --list 查看。不能省略 --exercise。");}}
            if(!auditOnly&&cpu==null)throw new IllegalArgumentException("请用 --cpu 指定 CPU.circ，并用 --exercise E05 指定已完成的题。");
            if(out==null)out=root.resolve("results").resolve((auditOnly?"selftest_":"run_")+LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss_SSS")));
            if(Files.exists(out))throw new IllegalArgumentException("结果目录已存在，请使用新的 --out 目录，避免覆盖旧报告。");Files.createDirectories(out);
            List<String[]> cases=new ArrayList<>();for(String[] c:tsv(root.resolve("cases.tsv")))if(ids.contains(c[0]))cases.add(c);
            if(cases.isEmpty())throw new IOException("No selected tests");
            for(String id:ids){boolean found=false;for(String[] c:cases)if(c[0].equals(id))found=true;if(!found)throw new IOException("Selected exercise has no cases: "+id);}
            if(!auditOnly){before=Files.readAllBytes(cpu);hash=sha(before);Files.write(out.resolve("CPU_original.circ"),before);sim=new P3Judge.Simulator(cpu,rom);layout=new StorageLayout(sim,out);}
            int i=0;for(String[] c:cases)run(c,++i,cases.size());
            if(auditOnly){P3Judge.write(out.resolve("selftest.txt"),"PASS: independent Python/Java models agree on "+cases.size()+" programs, "+totalCycles+" cycles, register and memory hashes after every cycle.\n");System.out.println("SELF-TEST PASS cases="+cases.size()+" cycles="+totalCycles);}
        }catch(Throwable e){fatal=e.toString();errors++;System.err.println("ERROR: "+fatal);exit=2;}
        try{if(before!=null&&!Arrays.equals(before,Files.readAllBytes(cpu))){fatal+=" 源电路在测试期间被外部修改。";errors++;}if(out!=null&&!auditOnly)report(fatal,hash);}catch(Exception e){errors++;System.err.println("Report error: "+e);}
        if(errors>0)exit=2;else if(failed>0)exit=1;
        if(out!=null)System.out.println("结果目录："+out+"；exit="+exit);System.exit(exit);
    }
}
