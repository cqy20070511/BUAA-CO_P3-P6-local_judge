import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import com.cburch.logisim.file.*;
import com.cburch.logisim.proj.*;
import com.cburch.logisim.circuit.*;
import com.cburch.logisim.comp.*;
import com.cburch.logisim.data.*;
import com.cburch.logisim.instance.*;
import com.cburch.logisim.std.wiring.*;
import com.cburch.logisim.std.memory.Rom;

public final class P3Judge {
    static final String VERSION="2.0.0";
    static final String[] SIGNALS={"Instr","pc","RegWrite","RegAddr","RegData","MemWrite","MemAddr","MemData"};
    static final int[] WIDTHS={32,32,1,5,32,1,32,32};
    static final Map<String,Integer> coverage=new TreeMap<>();
    static final Set<Integer> readAddresses=new HashSet<>(),writeAddresses=new HashSet<>(),registerDestinations=new HashSet<>();
    static long assertions=0,ignoredZeroWrites=0,startNanos;
    static Config config;
    static class Config {
        Path circuit,out,program;String rom;
        int random=12,maxCycles=50000,timeout=180;
        long seed=20261028L;boolean fullMemory=false,traceAll=false,selfTest=false;
    }
    static final class Failure extends Exception { Failure(String m){super(m);} }
    static final class TestError extends Exception { TestError(String m){super(m);} }
    static final class Result {
        String name,purpose,status="PASS",message="",directory="",phase="";
        int cycles=0,pc=0,word=0;long ms=0;
        final Deque<String[]> context=new ArrayDeque<>();
    }
    static final class Expected {
        int pc,word,next,reg,regData,memAddr,memData;
        boolean writesReg,writesMem,loads,branchTaken;
        String instruction;
    }
    /** Independent architectural state; add/sub intentionally wrap modulo 2^32. */
    static final class Reference {
        int pc=0x3000;final int[] regs=new int[32],memory=new int[3072];
        Expected decode(int w)throws TestError {
            Expected e=new Expected();e.pc=pc;e.word=w;e.next=pc+4;
            int op=w>>>26,rs=(w>>>21)&31,rt=(w>>>16)&31,rd=(w>>>11)&31,imm=(short)w;
            e.reg=rt;e.memData=regs[rt];
            if(w==0)e.instruction="nop";
            else if(op==0&&((w&63)==32||(w&63)==34)) {
                e.instruction=(w&63)==32?"add":"sub";e.writesReg=true;e.reg=rd;
                e.regData=(w&63)==32?regs[rs]+regs[rt]:regs[rs]-regs[rt];
            } else if(op==13){e.instruction="ori";e.writesReg=true;e.regData=regs[rs]|(w&65535);}
            else if(op==15){e.instruction="lui";e.writesReg=true;e.regData=w<<16;}
            else if(op==35||op==43) {
                e.instruction=op==35?"lw":"sw";e.memAddr=regs[rs]+imm;
                if((e.memAddr&3)!=0||Integer.compareUnsigned(e.memAddr,0x2ffc)>0)
                    throw new TestError(String.format("测试程序在 @%08x 访问无效地址 %08x；lw/sw 地址必须对齐且位于 0000..2ffc。",pc,e.memAddr));
                if(op==35){e.loads=true;e.writesReg=true;e.regData=memory[e.memAddr>>>2];}else e.writesMem=true;
            } else if(op==4){e.instruction="beq";e.branchTaken=regs[rs]==regs[rt];if(e.branchTaken)e.next=pc+4+(imm<<2);}
            else throw new TestError(String.format("测试程序包含未支持的机器码 @%08x: %08x (%s)",pc,w,Assembler.disasm(w)));
            return e;
        }
        void commit(Expected e){if(e.writesReg&&e.reg!=0)regs[e.reg]=e.regData;if(e.writesMem)memory[e.memAddr>>>2]=e.memData;regs[0]=0;pc=e.next;}
    }
    static final class Simulator {
        final LogisimFile file;final Project project;final Circuit main;
        final Map<String,Component> pins=new HashMap<>();
        final Component clock,rom;final Object contents;final Method clear,set;
        final List<String> warnings=new ArrayList<>();CircuitState state;
        Simulator(Path path,String selectedRom)throws Exception {
            file=new Loader(null).openLogisimFile(path.toFile());
            main=file.getCircuit("main");if(main==null)throw new TestError("找不到 main 电路。顶层名称必须为 main。");
            project=new Project(file);Component clk=null;
            for(Component c:main.getNonWires()) {
                if(c.getFactory() instanceof Pin) {
                    String label=label(c);if(pins.put(label,c)!=null)throw new TestError("顶层 Pin 名称重复："+label);
                }
                if(c.getFactory() instanceof Clock){if(clk!=null)throw new TestError("main 中发现多个时钟；请保留一个驱动 CPU 的内置 Clock。");clk=c;}
            }
            if(clk==null)throw new TestError("main 中未找到内置 Clock。评测工具按该时钟的真实上升沿推进 CPU。");clock=clk;
            Component reset=pins.get("reset");
            if(reset==null||reset.getEnd(0).getWidth().getWidth()!=1||!reset.getEnd(0).isOutput())throw new TestError("main 需要 1 位输入 Pin reset。");
            for(int n=0;n<SIGNALS.length;n++) {
                Component c=pins.get(SIGNALS[n]);
                if(c==null||c.getEnd(0).getWidth().getWidth()!=WIDTHS[n]||!c.getEnd(0).isInput())
                    throw new TestError("顶层输出 "+SIGNALS[n]+" 缺失、方向错误或位宽不是 "+WIDTHS[n]+"。");
            }
            for(Component c:pins.values())if(c.getEnd(0).isOutput()&&!label(c).equals("reset"))throw new TestError("顶层存在额外输入 "+label(c)+"，课程只允许 reset。");
            Set<Circuit> reachable=new HashSet<>();collect(main,reachable);
            List<Component> roms=new ArrayList<>();
            for(Circuit c:reachable) {
                if(c.getWidthIncompatibilityData()!=null&&!c.getWidthIncompatibilityData().isEmpty())warnings.add("电路 "+c.getName()+" 存在位宽不匹配。");
                for(Component x:c.getNonWires())if(x.getFactory() instanceof Rom && (selectedRom==null||c.getName().equals(selectedRom)||label(x).equals(selectedRom))) {
                    Object data=x.getAttributeSet().getValue(Rom.CONTENTS_ATTR);
                    Method width=data.getClass().getMethod("getValueWidth");width.setAccessible(true);
                    Method end=data.getClass().getMethod("getLastOffset");end.setAccessible(true);
                    if(((Integer)width.invoke(data))==32 && ((Long)end.invoke(data))==4095)roms.add(x);
                }
            }
            if(roms.size()!=1)throw new TestError("应找到一个可达的 4096×32 指令 ROM，实际候选数="+roms.size()+"。多个 ROM 时可使用 --rom 子电路名/ROM标签 指定。");
            rom=roms.get(0);contents=rom.getAttributeSet().getValue(Rom.CONTENTS_ATTR);
            clear=contents.getClass().getMethod("clear");clear.setAccessible(true);set=contents.getClass().getMethod("set",long.class,int.class);set.setAccessible(true);
            checkAppearance();
        }
        static String label(Component c){return c.getAttributeSet().containsAttribute(StdAttr.LABEL)?c.getAttributeSet().getValue(StdAttr.LABEL):"";}
        static void collect(Circuit c,Set<Circuit> found){if(!found.add(c))return;for(Component x:c.getNonWires())if(x.getFactory() instanceof SubcircuitFactory)collect(((SubcircuitFactory)x.getFactory()).getSubcircuit(),found);}
        void checkAppearance() {
            SortedMap<Location,Instance> ports=main.getAppearance().getPortOffsets(Direction.EAST);
            Map<String,Location> actual=new HashMap<>();
            for(Map.Entry<Location,Instance> e:ports.entrySet())actual.put(e.getValue().getAttributeValue(StdAttr.LABEL),e.getKey());
            boolean match=Location.create(-30,30).equals(actual.get("reset"));
            for(int n=0;n<SIGNALS.length;n++)match&=Location.create(0,n*10).equals(actual.get(SIGNALS[n]));
            if(!match)warnings.add("main 子电路外观的端口相对位置与课程图示不同；功能评测继续，但提交前需检查接口布局。");
        }
        void install(Assembler.Program p)throws Exception {
            clear.invoke(contents);for(int n=0;n<p.words.length;n++)set.invoke(contents,(long)n,p.words[n]);
        }
        void fresh(Assembler.Program p)throws Exception {install(p);state=new CircuitState(project,main);settle();reset();}
        void reset()throws Exception {setInput("reset",1);settle();expect("异步复位后的 pc","pc",0x3000);setInput("reset",0);settle();}
        void setInput(String name,int v){Component c=pins.get(name);Pin.FACTORY.setValue(state.getInstanceState(c),Value.createKnown(c.getEnd(0).getWidth(),v));state.markComponentAsDirty(c);}
        void settle()throws Failure {state.getPropagator().propagate();if(state.getPropagator().isOscillating())throw new Failure("组合逻辑传播未收敛（振荡）。请检查反馈回路。");}
        Value value(String name){return state.getValue(pins.get(name).getLocation());}
        int known(String name)throws Failure {Value v=value(name);if(!v.isFullyDefined())throw new Failure(name+" 出现未知值/冲突值："+v.toHexString());return v.toIntValue();}
        void expect(String reason,String name,int expected)throws Failure {
            assertions++;int got=known(name);if(got!=expected)throw new Failure(String.format("%s：%s 期望 0x%08x，实际 0x%08x",reason,name,expected,got));
        }
        void rising()throws Exception {
            Value prev=state.getValue(clock.getLocation());
            if(!prev.isFullyDefined())throw new Failure("内置时钟输出为未知值。");
            for(int n=0;n<10000;n++) {
                state.getPropagator().tick();settle();Value now=state.getValue(clock.getLocation());
                if(prev.equals(Value.FALSE)&&now.equals(Value.TRUE))return;prev=now;
            }
            throw new Failure("10000 次时钟半步内没有上升沿，请检查 Clock 的高低持续时间。");
        }
        String[] row(String phase,int cycle,Expected e) {
            StringBuilder actual=new StringBuilder();for(String n:SIGNALS)actual.append(n).append('=').append(value(n).toHexString()).append(' ');
            String expected=String.format("pc=%08x Instr=%08x RegWrite=%s RegAddr=%d RegData=%08x MemWrite=%s MemAddr=%08x MemData=%08x nextPC=%08x",e.pc,e.word,e.writesReg,e.reg,e.regData,e.writesMem,e.memAddr,e.memData,e.next);
            return new String[]{phase,Integer.toString(cycle),String.format("%08x",e.pc),Assembler.disasm(e.word),expected,actual.toString()};
        }
        void compare(Expected e)throws Exception {
            expect("执行地址","pc",e.pc);expect("取出的指令","Instr",e.word);
            int rw=known("RegWrite"),mw=known("MemWrite");assertions+=2;
            // Writes to architectural $0 may be suppressed in the GRF or at the controller.
            if(e.writesReg&&e.reg!=0) {
                expect("寄存器写使能","RegWrite",1);expect("寄存器写地址","RegAddr",e.reg);expect("寄存器写数据","RegData",e.regData);
            } else if(rw==1) {
                expect("当前指令不应写入非零寄存器","RegAddr",0);ignoredZeroWrites++;
            }
            if(mw!=(e.writesMem?1:0))throw new Failure("内存写使能 MemWrite 期望 "+(e.writesMem?1:0)+"，实际 "+mw);
            if(e.writesMem||e.loads)expect("访存地址","MemAddr",e.memAddr);
            if(e.writesMem)expect("内存写数据","MemData",e.memData);
        }
    }
    static void budget()throws TestError {if((System.nanoTime()-startNanos)/1_000_000_000L>config.timeout)throw new TestError("整个评测超过 "+config.timeout+" 秒，请增大 --timeout 或减少随机用例数量。");}
    static String h(String s){return s==null?"":s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;");}
    static String json(String s){StringBuilder b=new StringBuilder("\"");for(char c:s.toCharArray()){if(c=='"'||c=='\\')b.append('\\').append(c);else if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}return b.append('"').toString();}
    static void write(Path path,String s)throws IOException {Files.createDirectories(path.getParent());Files.write(path,s.getBytes(StandardCharsets.UTF_8));}
    static void csv(PrintWriter out,String[] cells){for(int n=0;n<cells.length;n++){if(n>0)out.print(',');out.print('"');out.print(cells[n].replace("\"","\"\""));out.print('"');}out.println();}
    static void artifacts(Path dir,Assembler.Program p,String prefix)throws IOException {
        write(dir.resolve(prefix+".asm"),p.source);StringBuilder hex=new StringBuilder("v2.0 raw\n"),listing=new StringBuilder("PC        WORD      BINARY                                INSTRUCTION / SOURCE\n");
        for(int n=0;n<p.words.length;n++){int w=p.words[n];hex.append(String.format("%08x%n",w));String binary=String.format("%32s",Integer.toBinaryString(w)).replace(' ','0');listing.append(String.format("%08x  %08x  %s  %s | %s%n",0x3000+n*4,w,binary,Assembler.disasm(w),p.lines[n]));}
        write(dir.resolve(prefix+".hex"),hex.toString());write(dir.resolve(prefix+".listing.txt"),listing.toString());
    }
    static void phase(Simulator sim,Assembler.Program p,Result r,String phase,PrintWriter trace)throws Exception {
        Reference ref=new Reference();r.phase=phase;
        for(int cycle=0;cycle<config.maxCycles;cycle++) {
            budget();int index=(ref.pc-0x3000)/4;
            if((ref.pc&3)!=0||index<0||index>=p.words.length)throw new TestError(String.format("参考程序跳到未定义指令 @%08x，检查分支目标。",ref.pc));
            Expected e=ref.decode(p.words[index]);r.pc=e.pc;r.word=e.word;
            String[] row=sim.row(phase,cycle,e);r.context.addLast(row);if(r.context.size()>24)r.context.removeFirst();if(trace!=null)csv(trace,row);
            sim.compare(e);coverage.put(e.instruction,coverage.getOrDefault(e.instruction,0)+1);
            if(e.instruction.equals("beq")) {
                String k=e.branchTaken?"branch_taken":"branch_not_taken";coverage.put(k,coverage.getOrDefault(k,0)+1);
                int target=e.pc+4+(((short)e.word)<<2);String direction=target<e.pc?"before":target==e.pc?"self":"after";
                k="beq_"+(e.branchTaken?"taken_":"not_taken_")+direction;coverage.put(k,coverage.getOrDefault(k,0)+1);
            }
            if(e.loads){readAddresses.add(e.memAddr);coverage.put("unique_DM_read_words",readAddresses.size());}
            if(e.writesMem){writeAddresses.add(e.memAddr);coverage.put("unique_DM_written_words",writeAddresses.size());}
            if(e.writesReg){registerDestinations.add(e.reg);coverage.put("unique_register_destinations",registerDestinations.size());}
            ref.commit(e);sim.rising();r.cycles++;sim.expect("时钟上升沿后的 PC","pc",e.next);
            if(ref.pc==0x3000+p.words.length*4)return;
            if(index==p.words.length-1&&e.instruction.equals("beq")&&e.branchTaken&&e.next==e.pc)return;
        }
        throw new TestError("参考程序在 "+config.maxCycles+" 个周期内未终止。程序需落到末尾之后，或以最后一条 beq 自跳转结束；可增大 --max-cycles。");
    }
    static Result run(Simulator sim,TestSuite.Case c,int index)throws Exception {
        Result r=new Result();r.name=c.name;r.purpose=c.purpose;r.directory=String.format("cases/%03d_%s",index,c.name.replaceAll("[^a-zA-Z0-9_.-]","_"));
        Path dir=config.out.resolve(r.directory);Files.createDirectories(dir);artifacts(dir,c.program,"program");
        if(c.warmup!=null)artifacts(dir,c.warmup,"warmup");long start=System.nanoTime();
        PrintWriter trace=config.traceAll?new PrintWriter(Files.newBufferedWriter(dir.resolve("trace.csv"),StandardCharsets.UTF_8)):null;
        if(trace!=null)csv(trace,new String[]{"phase","cycle","pc","instruction","expected","actual"});
        try {
            if(c.warmup!=null){sim.fresh(c.warmup);phase(sim,c.warmup,r,"warmup",trace);sim.install(c.program);sim.reset();}
            else sim.fresh(c.program);
            phase(sim,c.program,r,"test",trace);
        } catch(Failure e){r.status="WA";r.message=e.getMessage();}
        catch(TestError e){r.status="TEST_ERROR";r.message=e.getMessage();}
        catch(Exception e){r.status="ERROR";r.message=e.getClass().getSimpleName()+": "+e.getMessage();}
        finally{if(trace!=null)trace.close();}
        r.ms=(System.nanoTime()-start)/1_000_000L;
        if(!r.status.equals("PASS")) {
            try(PrintWriter out=new PrintWriter(Files.newBufferedWriter(dir.resolve("failure_context.csv"),StandardCharsets.UTF_8))){csv(out,new String[]{"phase","cycle","pc","instruction","expected","actual"});for(String[] row:r.context)csv(out,row);}
            String detail="状态: "+r.status+"\n用例: "+r.name+"\n阶段: "+r.phase+"\n已执行周期: "+r.cycles+"\nPC: "+String.format("%08x",r.pc)+"\n指令: "+Assembler.disasm(r.word)+"\n机器码: "+String.format("%08x",r.word)+"\n原因: "+r.message+"\n";
            if(r.message.contains("PC")||r.message.contains("pc"))detail+="定位建议: 检查 PC 的 D/WE/reset/clk、NPC 输入。若当前 GUI 正常而文件重新打开后失败，检查自定义外观方向和端口在重新加载后的位置。评测器不自动旋转或修复电路。\n";
            write(dir.resolve("failure.txt"),detail);
        }
        return r;
    }
    static void report(List<Result> results,List<String> warnings,String fatal,String hash)throws IOException {
        int passed=0;for(Result r:results)if(r.status.equals("PASS"))passed++;
        String verdict=fatal.isEmpty()?(passed==results.size()?"PASS":"FAIL"):"ERROR";
        StringBuilder html=new StringBuilder("<!doctype html><html lang=zh-CN><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>P3 本地评测报告</title><style>body{font:15px/1.65 system-ui,Segoe UI,sans-serif;background:#f5f7fb;color:#162238;margin:0}main{max-width:1100px;margin:32px auto;padding:28px;background:white;border-radius:16px}h1{margin:0 0 14px}table{border-collapse:collapse;width:100%;margin-top:20px}td,th{text-align:left;border-bottom:1px solid #e4e8ef;padding:10px;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f8;padding:12px;border-radius:8px}.PASS{color:#137b41}.WA,.FAIL,.ERROR,.TEST_ERROR{color:#bc2934}a{color:#245bc5}.meta{color:#536078}.box{padding:12px;border-left:4px solid #e4ac35;background:#fff8e5}summary{cursor:pointer}code{background:#eef2f7;padding:1px 4px}</style><main><h1>P3 本地评测：");
        html.append("<span class='").append(verdict).append("'>").append(verdict).append("</span></h1><p>").append(passed).append(" / ").append(results.size()).append(" 个用例通过；").append(assertions).append(" 项信号比较。</p><div class=meta>电路：").append(h(config.circuit.toString())).append("<br>SHA-256：").append(h(hash)).append("<br>seed=").append(config.seed).append("；随机用例=").append(config.random).append("；版本=").append(VERSION).append("</div>");
        html.append("<p>按本课程八条指令运行；add/sub 按 32 位截断，无延迟槽。写 $0 的数据忽略，允许电路抑制对 $0 的写使能。只比较当前指令实际使用的地址/数据。电路按保存文件重新加载，评测器不会修改源文件或自动修复方向。</p>");
        if(!fatal.isEmpty())html.append("<pre class=ERROR>").append(h(fatal)).append("</pre>");
        for(String w:warnings)html.append("<p class=box>").append(h(w)).append("</p>");
        html.append("<table><tr><th>结果</th><th>用例 / 目的</th><th>周期 / 耗时</th><th>定位与材料</th></tr>");
        StringBuilder j=new StringBuilder("{\n\"version\":").append(json(VERSION)).append(",\n\"verdict\":").append(json(verdict)).append(",\n\"circuit\":").append(json(config.circuit.toString())).append(",\n\"sha256\":").append(json(hash)).append(",\n\"seed\":").append(config.seed).append(",\n\"assertions\":").append(assertions).append(",\n\"fatal\":").append(json(fatal)).append(",\n\"results\":[");
        boolean first=true;
        for(Result r:results) {
            html.append("<tr><td class='").append(r.status).append("'>").append(r.status).append("</td><td><b>").append(h(r.name)).append("</b><br>").append(h(r.purpose)).append("</td><td>").append(r.cycles).append("<br>").append(r.ms).append(" ms</td><td><a href='").append(r.directory).append("/program.asm'>汇编</a> · <a href='").append(r.directory).append("/program.hex'>ROM 镜像</a> · <a href='").append(r.directory).append("/program.listing.txt'>机器码</a>");
            if(!r.status.equals("PASS"))html.append("<details open><summary>首个错误 @").append(String.format("%08x",r.pc)).append("</summary><pre>").append(h(r.message)).append("\n").append(h(Assembler.disasm(r.word))).append("</pre><a href='").append(r.directory).append("/failure.txt'>错误说明</a> · <a href='").append(r.directory).append("/failure_context.csv'>前后信号记录</a></details>");
            html.append("</td></tr>");
            if(!first)j.append(',');first=false;
            j.append("\n{\"name\":").append(json(r.name)).append(",\"status\":").append(json(r.status)).append(",\"cycles\":").append(r.cycles).append(",\"ms\":").append(r.ms).append(",\"pc\":").append(json(String.format("%08x",r.pc))).append(",\"message\":").append(json(r.message)).append(",\"directory\":").append(json(r.directory)).append('}');
        }
        html.append("</table><p>动态指令覆盖：").append(h(coverage.toString())).append("</p><p class=meta>本地测试不等于通过官方评测；TEST_ERROR 表示测试程序本身越界、未支持或未在预算内结束，不应直接当作 CPU 错误。</p></main></html>");
        j.append("\n],\n\"coverage\":{");first=true;for(Map.Entry<String,Integer> e:coverage.entrySet()){if(!first)j.append(',');first=false;j.append(json(e.getKey())).append(':').append(e.getValue());}j.append("}\n}\n");
        write(config.out.resolve("report.html"),html.toString());write(config.out.resolve("summary.json"),j.toString());
        StringBuilder txt=new StringBuilder(verdict+" "+passed+"/"+results.size()+"\nCircuit: "+config.circuit+"\nSHA256: "+hash+"\nSeed: "+config.seed+"\n");
        if(!fatal.isEmpty())txt.append(fatal).append('\n');for(Result r:results)txt.append(r.status).append(' ').append(r.name).append(" cycles=").append(r.cycles).append(" ").append(r.message).append('\n');write(config.out.resolve("summary.txt"),txt.toString());
    }
    static Config args(String[] args) {
        Config c=new Config();
        for(int n=0;n<args.length;n++) {
            String a=args[n];
            if(a.equals("--self-test")){c.selfTest=true;continue;}
            if(a.equals("--full-memory")){c.fullMemory=true;continue;}
            if(a.equals("--trace-all")){c.traceAll=true;continue;}
            if(a.equals("--help")||a.equals("-h")){help();System.exit(0);}
            if(n+1>=args.length)throw new IllegalArgumentException("Missing value for "+a);String v=args[++n];
            if(a.equals("--circuit"))c.circuit=Paths.get(v).toAbsolutePath();
            else if(a.equals("--out"))c.out=Paths.get(v).toAbsolutePath();
            else if(a.equals("--program"))c.program=Paths.get(v).toAbsolutePath();
            else if(a.equals("--random"))c.random=Integer.parseInt(v);
            else if(a.equals("--seed"))c.seed=Long.parseLong(v);
            else if(a.equals("--max-cycles"))c.maxCycles=Integer.parseInt(v);
            else if(a.equals("--timeout"))c.timeout=Integer.parseInt(v);
            else if(a.equals("--rom"))c.rom=v;
            else throw new IllegalArgumentException("Unknown option: "+a);
        }
        if(c.random<0||c.random>10000||c.maxCycles<1||c.timeout<1)throw new IllegalArgumentException("Invalid random/max-cycles/timeout value");
        if(!c.selfTest&&c.circuit==null)throw new IllegalArgumentException("请指定 --circuit CPU.circ");
        if(c.out==null)c.out=Paths.get("results",LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss_SSS"))).toAbsolutePath();
        return c;
    }
    static void help(){System.out.println("P3Judge "+VERSION+"\n--circuit FILE.circ [--out DIR] [--random 12] [--seed 20261028]\n[--program FILE.asm|FILE.hex|FILE.txt] [--full-memory] [--trace-all]\n[--max-cycles 50000] [--timeout 180] [--rom CIRCUIT_OR_LABEL]\n--self-test\nExit: 0 pass, 1 CPU mismatch, 2 tool/test/setup error.");}
    static void selfTest()throws Exception {
        Assembler.Program p=Assembler.assemble("known",".text 0x3000\nadd $t0,$t1,$t2\nsub $t0,$t1,$t2\nori $t0,$t1,0x1234\nlw $t0,4($t1)\nsw $t0,-4($t1)\nbeq $t0,$t1,target\nlui $t0,0x1234\nnop\ntarget: beq $0,$0,target\n");
        int[] expected={0x012a4020,0x012a4022,0x35281234,0x8d280004,0xad28fffc,0x11090002,0x3c081234,0,0x1000ffff};
        if(!Arrays.equals(p.words,expected))throw new AssertionError("assembler known encodings");
        Reference r=new Reference();r.regs[1]=0x7fffffff;r.regs[2]=1;Expected e=r.decode(0x00221820);if(e.regData!=0x80000000)throw new AssertionError("addition wrap");
        r.regs[1]=0;r.regs[2]=1;e=r.decode(0x00221822);if(e.regData!=-1)throw new AssertionError("subtraction wrap");
        r.regs[1]=0x12340000;e=r.decode(0x34228000);if(e.regData!=0x12348000)throw new AssertionError("ori zero extension");
        e=r.decode(0x1000ffff);if(e.next!=0x3000)throw new AssertionError("negative branch offset");
        r.regs[1]=-4;r.regs[2]=0x89abcdef;e=r.decode(0xac220004);r.commit(e);if(r.memory[0]!=0x89abcdef)throw new AssertionError("store signed base");
        e=r.decode(0x8c230004);if(e.regData!=0x89abcdef)throw new AssertionError("load");
        r.regs[1]=0x7fffffff;e=r.decode(0x3420ffff);r.commit(e);if(r.regs[0]!=0)throw new AssertionError("zero register");
        boolean rejected=false;try{Assembler.assemble("bad","addi $1,$0,1");}catch(IllegalArgumentException ex){rejected=true;}if(!rejected)throw new AssertionError("unsupported opcode");
        if(TestSuite.create(2,1,true).size()!=29)throw new AssertionError("suite count");
        System.out.println("SELF-TEST PASS: known machine encodings, branch offsets, overflow, signed addresses, zero register, input validation.");
    }
    public static void main(String[] argv) {
        System.setProperty("java.awt.headless","true");System.setProperty("java.util.prefs.PreferencesFactory","MemoryPreferencesFactory");
        List<Result> results=new ArrayList<>();List<String> warnings=new ArrayList<>();String fatal="",hash="";int exit=0;startNanos=System.nanoTime();
        try {
            config=args(argv);if(config.selfTest){selfTest();System.exit(0);}
            Files.createDirectories(config.out);byte[] before=Files.readAllBytes(config.circuit);
            StringBuilder hs=new StringBuilder();for(byte v:MessageDigest.getInstance("SHA-256").digest(before))hs.append(String.format("%02x",v&255));hash=hs.toString();
            System.out.println("P3 本地评测机 "+VERSION+"\n电路："+config.circuit+"\n报告："+config.out+"\n种子："+config.seed);
            Simulator sim=new Simulator(config.circuit,config.rom);warnings.addAll(sim.warnings);
            List<TestSuite.Case> cases;
            if(config.program!=null){Assembler.Program p=Assembler.read(config.program);cases=Collections.singletonList(new TestSuite.Case("custom_program","用户提供的程序："+config.program,p,null));}
            else cases=TestSuite.create(config.random,config.seed,config.fullMemory);
            int i=0;for(TestSuite.Case c:cases){budget();Result r=run(sim,c,++i);results.add(r);System.out.printf(Locale.ROOT,"[%02d/%02d] %-10s %-24s %6d cycles %6d ms%n",i,cases.size(),r.status,r.name,r.cycles,r.ms);if(!r.message.isEmpty())System.out.println("  "+r.message);if(!r.status.equals("PASS"))exit=r.status.equals("WA")?Math.max(exit,1):2;}
            if(!Arrays.equals(before,Files.readAllBytes(config.circuit)))throw new IOException("源电路在评测期间发生外部修改，请保存后重新运行。");
        } catch(Throwable e) {exit=2;fatal=e.getClass().getSimpleName()+": "+e.getMessage();System.err.println("ERROR: "+fatal);}
        try{if(config!=null&&config.circuit!=null)report(results,warnings,fatal,hash);}catch(Exception e){exit=2;System.err.println("报告写入失败："+e);}
        if(config!=null&&!config.selfTest)System.out.println("\n完成。退出码="+exit+"；报告="+config.out.resolve("report.html"));
        System.exit(exit);
    }
}
