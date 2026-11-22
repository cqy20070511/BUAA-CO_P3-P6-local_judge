import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.*;

/** One complete headless Logisim simulation job, launched by the desktop UI. */
public final class AutomationRunner {
    static StorageLayout layout;static boolean strictZero=true,resetMatrix=true;static Path currentDir;
    static int lastSample;static long start;static P3Judge.Simulator sim;
    static void check(TraceArchive trace,String phase,int cycle,String event,int pc,int word,P3Judge.Reference ref,Assembler.Program p)throws Exception {
        int[][] state=layout.capture(sim);lastSample=trace.sample(sim,phase,cycle,event,pc,word,ref,state,p);
        String mismatch=layout.compare(state,ref,p,strictZero);
        if(mismatch!=null)throw new P3Judge.Failure("内部存储不一致（sample="+lastSample+", "+event+"）\n"+mismatch+(mismatch.contains(" R0")?"\n这是物理 $0 寄存器检查。若读口已固定输出 0，可在界面关闭严格物理 $0 检查，单独验证架构行为。":""));
        sim.expect("内部状态采样时 PC","pc",ref.pc);
    }
    static int clock(){return sim.state.getValue(sim.clock.getLocation()).toIntValue();}
    static void tick()throws Exception {sim.state.getPropagator().tick();sim.settle();}
    static void toLow(TraceArchive t,String phase,int cycle,int pc,int word,P3Judge.Reference ref,Assembler.Program p)throws Exception {
        for(int n=0;clock()!=0;n++){if(n>10000)throw new P3Judge.TestError("Clock cannot reach low");tick();check(t,phase,cycle,"falling_or_high_hold",pc,word,ref,p);}
    }
    static void execute(Assembler.Program p,List<MarsOracle.Step> steps,P3Judge.Result r,String phase,TraceArchive trace)throws Exception {
        P3Judge.Reference ref=new P3Judge.Reference();r.phase=phase;
        for(int cycle=0;cycle<steps.size();cycle++) {
            P3Judge.budget();MarsOracle.Step s=steps.get(cycle);P3Judge.Expected e=s.e;r.pc=e.pc;r.word=e.word;
            check(trace,phase,cycle,"pre_edge",e.pc,e.word,ref,p);
            String[] row=sim.row(phase,cycle,e);r.context.addLast(row);if(r.context.size()>24)r.context.removeFirst();sim.compare(e);
            toLow(trace,phase,cycle,e.pc,e.word,ref,p);
            for(int n=0;;n++) {if(n>10000)throw new P3Judge.TestError("Clock cannot reach rising edge");tick();if(clock()==1)break;check(trace,phase,cycle,"low_hold",e.pc,e.word,ref,p);}
            ref.pc=e.next;System.arraycopy(s.regs,0,ref.regs,0,32);if(e.writesMem)ref.memory[e.memAddr>>>2]=e.memData;
            r.cycles++;check(trace,phase,cycle,"post_edge",e.pc,e.word,ref,p);
            P3Judge.coverage.put(e.instruction,P3Judge.coverage.getOrDefault(e.instruction,0)+1);
        }
    }
    static void reset(P3Judge.Reference previous,Assembler.Program installed,TraceArchive t,String mode)throws Exception {
        if(mode.equals("low")||mode.equals("across_rising"))toLow(t,"reset",0,previous.pc,0,previous,installed);
        // high mode starts immediately after the last completed rising edge.
        if(mode.equals("high")&&clock()!=1)throw new P3Judge.TestError("Reset high-phase setup failed");
        P3Judge.Reference zero=new P3Judge.Reference();sim.setInput("reset",1);sim.settle();
        check(t,"reset_"+mode,0,"assert_without_clock_edge",0x3000,0,zero,installed);
        if(mode.equals("across_rising")) {
            for(int n=0;;n++){if(n>10000)throw new P3Judge.TestError("Reset clock timeout");tick();check(t,"reset_"+mode,0,"hold_reset_across_edge",0x3000,0,zero,installed);if(clock()==1)break;}
        }
        sim.setInput("reset",0);sim.settle();check(t,"reset_"+mode,0,"release_without_clock_edge",0x3000,0,zero,installed);
    }
    static void expected(List<MarsOracle.Step> steps,Path file)throws Exception {
        try(PrintWriter w=new PrintWriter(Files.newBufferedWriter(file,StandardCharsets.UTF_8))) {
            P3Judge.csv(w,new String[]{"cycle","pc","Instr","instruction","RegWrite","RegAddr","RegData","MemWrite","MemAddr","MemData","nextPC","registers_after"});int i=0;
            for(MarsOracle.Step s:steps){P3Judge.Expected e=s.e;StringBuilder r=new StringBuilder();for(int a:s.regs)r.append(String.format("%08x ",a));
                P3Judge.csv(w,new String[]{""+i++,String.format("%08x",e.pc),String.format("%08x",e.word),Assembler.disasm(e.word),e.writesReg?(e.reg==0?"0 or 1 ($0)":"1"):"0 (or ineffective $0 write)",e.writesReg?""+e.reg:"-",e.writesReg&&e.reg!=0?String.format("%08x",e.regData):"-",e.writesMem?"1":"0",e.loads||e.writesMem?String.format("%08x",e.memAddr):"-",e.writesMem?String.format("%08x",e.memData):"-",String.format("%08x",e.next),r.toString()});
            }
        }
    }
    static P3Judge.Reference finalState(List<MarsOracle.Step> steps){P3Judge.Reference ref=new P3Judge.Reference();for(MarsOracle.Step s:steps){ref.pc=s.e.next;System.arraycopy(s.regs,0,ref.regs,0,32);if(s.e.writesMem)ref.memory[s.e.memAddr>>>2]=s.e.memData;}return ref;}
    static void exportCircuit(Path source,Path out,Assembler.Program p)throws Exception {
        DocumentBuilderFactory f=DocumentBuilderFactory.newInstance();f.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);f.setExpandEntityReferences(false);
        Document d=f.newDocumentBuilder().parse(source.toFile());NodeList comps=d.getElementsByTagName("comp");Element rom=null;
        for(int i=0;i<comps.getLength();i++){Element e=(Element)comps.item(i);if(e.getAttribute("name").equals("ROM")&&e.getAttribute("loc").equals(sim.rom.getLocation().toString().replace(" ",""))){String cn=((Element)e.getParentNode()).getAttribute("name");if(sim.file.getCircuit(cn).getNonWires().contains(sim.rom))rom=e;}}
        if(rom==null)throw new P3Judge.TestError("无法定位用于导出副本的指令 ROM");Element content=null;
        NodeList attrs=rom.getElementsByTagName("a");for(int i=0;i<attrs.getLength();i++)if(((Element)attrs.item(i)).getAttribute("name").equals("contents"))content=(Element)attrs.item(i);
        if(content==null){content=d.createElement("a");content.setAttribute("name","contents");rom.appendChild(content);}
        StringBuilder text=new StringBuilder("addr/data: 12 32\n");for(int w:p.words)text.append(String.format("%08x\n",w));content.setTextContent(text.toString());
        Transformer t=TransformerFactory.newInstance().newTransformer();t.setOutputProperty(OutputKeys.ENCODING,"UTF-8");t.transform(new DOMSource(d),new StreamResult(out.toFile()));
    }
    static P3Judge.Result run(TestSuite.Case c,int index,String resetMode)throws Exception {
        P3Judge.Result r=new P3Judge.Result();r.name=c.name;r.purpose=c.purpose;r.directory=String.format("cases/%03d_%s",index,c.name);currentDir=P3Judge.config.out.resolve(r.directory);Files.createDirectories(currentDir);
        P3Judge.artifacts(currentDir,c.program,"program");long started=System.nanoTime();lastSample=0;
        try(TraceArchive trace=new TraceArchive(currentDir,layout)) {
            List<MarsOracle.Step> main=MarsOracle.prepare(c.program,currentDir,P3Judge.config.maxCycles);expected(main,currentDir.resolve("expectations.csv"));
            List<MarsOracle.Step> warm=null;if(c.warmup!=null){Path wd=currentDir.resolve("warmup");Files.createDirectories(wd);P3Judge.artifacts(wd,c.warmup,"program");warm=MarsOracle.prepare(c.warmup,wd,P3Judge.config.maxCycles);expected(warm,wd.resolve("expectations.csv"));}
            exportCircuit(P3Judge.config.circuit,currentDir.resolve("CPU_loaded.circ"),c.program);
            if(warm!=null){sim.fresh(c.warmup);execute(c.warmup,warm,r,"warmup",trace);reset(finalState(warm),c.warmup,trace,resetMode);sim.install(c.program);sim.settle();}
            else {sim.fresh(c.program);check(trace,"initial_reset",0,"reset_released",0x3000,c.program.words[0],new P3Judge.Reference(),c.program);}
            execute(c.program,main,r,"test",trace);
        }catch(P3Judge.Failure e){r.status="WA";r.message=e.getMessage();}
        catch(P3Judge.TestError|IllegalArgumentException e){r.status="TEST_ERROR";r.message=e.getMessage();}
        catch(Exception e){r.status="ERROR";r.message=e.toString();StringWriter sw=new StringWriter();e.printStackTrace(new PrintWriter(sw));P3Judge.write(currentDir.resolve("exception.txt"),sw.toString());}
        r.ms=(System.nanoTime()-started)/1_000_000;
        if(!r.status.equals("PASS")) {
            int indexPC=(r.pc-0x3000)/4;Assembler.Program active=r.phase.equals("warmup")&&c.warmup!=null?c.warmup:c.program;
            String line=indexPC>=0&&indexPC<active.lines.length?active.lines[indexPC]:"reset/setup";
            r.message+="\n源代码："+line+"\n阶段："+r.phase+"；已执行周期："+r.cycles+"；采样编号："+lastSample;
            P3Judge.write(currentDir.resolve("failure.txt"),r.status+"\nPC="+String.format("%08x",r.pc)+"\n"+r.message);
            try(PrintWriter w=new PrintWriter(Files.newBufferedWriter(currentDir.resolve("failure_context.csv"),StandardCharsets.UTF_8))){for(String[] row:r.context)P3Judge.csv(w,row);}
            if(lastSample>0)P3Judge.write(currentDir.resolve("failure_state.csv"),TraceArchive.read(currentDir.resolve("state.p3trace.gz"),lastSample).csv());
        }
        return r;
    }
    static TestSuite.Case resetCase(String mode) {
        TestSuite.B warm=new TestSuite.B();for(int r=1;r<32;r++)warm.li(r,0x12340000+r);for(int a:new int[]{0,4,0xffc,0x1000,0x1ffc,0x2000,0x2ffc})warm.emit("sw $1, %d($0)",a);
        TestSuite.B check=new TestSuite.B();check.emit("ori $1, $0, 1").emit("sw $1, 0($0)").emit("lw $2, 0($0)");
        return new TestSuite.Case("reset_"+mode,"Dirty state, asynchronous reset at "+mode+", restart",Assembler.assemble("reset",check.end()),Assembler.assemble("dirty",warm.end()));
    }
    public static void main(String[] args) {
        System.setProperty("java.awt.headless","true");System.setProperty("java.util.prefs.PreferencesFactory","MemoryPreferencesFactory");
        List<P3Judge.Result> results=new ArrayList<>();List<String> warnings=new ArrayList<>();String fatal="",hash="";int exit=0;P3Judge.startNanos=System.nanoTime();
        try {
            List<String> filtered=new ArrayList<>();for(String a:args)if(a.equals("--architectural-zero"))strictZero=false;else if(a.equals("--no-reset-matrix"))resetMatrix=false;else filtered.add(a);
            P3Judge.config=P3Judge.args(filtered.toArray(new String[0]));Files.createDirectories(P3Judge.config.out);
            byte[] before=Files.readAllBytes(P3Judge.config.circuit);StringBuilder b=new StringBuilder();for(byte x:MessageDigest.getInstance("SHA-256").digest(before))b.append(String.format("%02x",x&255));hash=b.toString();
            Files.write(P3Judge.config.out.resolve("CPU_original.circ"),before);
            System.out.println("P3 自动评测 v2：MARS 预执行 → Logisim 仿真 → 全存储逐周期比较\n电路："+P3Judge.config.circuit+"\n报告："+P3Judge.config.out);
            sim=new P3Judge.Simulator(P3Judge.config.circuit,P3Judge.config.rom);warnings.addAll(sim.warnings);layout=new StorageLayout(sim,P3Judge.config.out);
            System.out.println("已映射 "+layout.slots.size()+" 个存储元件。严格物理 $0="+strictZero);
            warnings.add("MARS 4.5 实际汇编和指令执行；参考侧 add/sub 用 addu/subu 实现课程规定的溢出截断，导入 CPU 的机器码保持 add/sub。text 上限扩至 0x7000，寄存器初值全部归零，无延迟槽。");
            warnings.add("逐周期读取全部 8 个输出；无效地址/写数据为 don't-care。全量内部值以无损差分保存在 state.p3trace.gz，可从界面导出任意样本。signals.csv 给出样本编号；expectations.csv 为仿真前生成的 MARS 期望。");
            if(!strictZero)warnings.add("架构 $0 模式：物理 R0 仍完整采样，但不比较其内容；$0 的实际读取行为由程序检查。此选项不验证物理 R0 恒零。");
            List<TestSuite.Case> cases=new ArrayList<>();
            if(P3Judge.config.program!=null){Assembler.Program p=Assembler.read(P3Judge.config.program);cases.add(new TestSuite.Case("custom_program","手写程序",p,null));}
            else cases.addAll(TestSuite.create(P3Judge.config.random,P3Judge.config.seed,P3Judge.config.fullMemory));
            if(resetMatrix)for(String mode:new String[]{"low","high","across_rising"})cases.add(resetCase(mode));
            int i=0;for(TestSuite.Case c:cases){P3Judge.budget();String mode=c.name.startsWith("reset_")?c.name.substring(6):"low";P3Judge.Result r=run(c,++i,mode);results.add(r);System.out.println("["+i+"/"+cases.size()+"] "+r.status+" "+c.name+" cycles="+r.cycles+" "+r.ms+" ms");if(!r.message.isEmpty())System.out.println(r.message);if(!r.status.equals("PASS"))exit=r.status.equals("WA")?Math.max(exit,1):2;}
            if(!Arrays.equals(before,Files.readAllBytes(P3Judge.config.circuit)))throw new IOException("源文件在运行期间被外部修改，请重新测试。");
        }catch(Throwable e){exit=2;fatal=e.toString();System.err.println("ERROR: "+fatal);e.printStackTrace();}
        try{if(P3Judge.config!=null){P3Judge.report(results,warnings,fatal,hash);StringBuilder tsv=new StringBuilder();for(P3Judge.Result r:results)tsv.append(r.status).append('\t').append(r.name).append('\t').append(r.cycles).append('\t').append(r.message.replace('\n',' ').replace('\r',' ').replace('\t',' ')).append('\t').append(r.directory).append('\n');P3Judge.write(P3Judge.config.out.resolve("results.tsv"),tsv.toString());Path report=P3Judge.config.out.resolve("report.html");String html=new String(Files.readAllBytes(report),StandardCharsets.UTF_8);html=html.replace("项信号比较","项信号及存储值比较");
            StringBuilder links=new StringBuilder("<h2>逐周期记录与复现</h2><p><a href='storage_map.csv'>内部存储映射</a> · <a href='CPU_original.circ'>原电路快照</a></p><ul>");
            for(P3Judge.Result r:results){links.append("<li>").append(P3Judge.h(r.name));for(String f:new String[]{"CPU_loaded.circ","signals.csv","expectations.csv","state.p3trace.gz","failure_state.csv"})if(Files.exists(P3Judge.config.out.resolve(r.directory).resolve(f)))links.append(" · <a href='").append(r.directory).append('/').append(f).append("'>").append(f).append("</a>");links.append("</li>");}links.append("</ul>");P3Judge.write(report,html.replace("</main>",links+"</main>"));
            System.out.println("完成，退出码="+exit+"。报告："+report);}}
        catch(Exception e){exit=2;e.printStackTrace();}System.exit(exit);
    }
}
