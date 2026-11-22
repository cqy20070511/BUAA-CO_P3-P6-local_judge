import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import com.cburch.hex.HexModel;
import com.cburch.logisim.circuit.*;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.data.*;
import com.cburch.logisim.instance.StdAttr;
import com.cburch.logisim.std.memory.*;
import com.cburch.logisim.std.wiring.Pin;

/** Maps storage through actual read wiring, not screen coordinates or repeated R0 labels. */
final class StorageLayout {
    static final class Slot {
        Component component;List<Component> route;String path,kind,role;int count,reg=-1,xor;
        CircuitState state(CircuitState root){for(Component c:route)root=((SubcircuitFactory)c.getFactory()).getSubstate(root,c);return root;}
        int[] read(CircuitState root)throws Exception {
            CircuitState s=state(root);
            if(kind.equals("Register"))return new int[]{getRegister(s,component)};
            Object data=kind.equals("ROM")?component.getAttributeSet().getValue(Rom.CONTENTS_ATTR):contents(s.getData(component));
            HexModel mem=(HexModel)data;int[] a=new int[count];for(int i=0;i<a.length;i++)a[i]=mem.get(i);return a;
        }
    }
    final List<Slot> slots=new ArrayList<>();
    StorageLayout(P3Judge.Simulator sim,Path output)throws Exception {
        scan(sim,sim.main,new ArrayList<Component>(),"main");
        int pc=0,ram=0,rom=0;Set<Integer> regs=new HashSet<>();
        for(Slot s:slots){if(s.role.equals("PC"))pc++;else if(s.role.equals("DM"))ram++;else if(s.role.equals("IM"))rom++;else if(s.reg>=0)regs.add(s.reg);}
        if(pc!=1||ram!=1||rom!=1||!regs.containsAll(range(1,32)))throw new P3Judge.TestError("内部存储自动识别不完整：PC="+pc+", RAM="+ram+", ROM="+rom+", GRF="+regs.size()+"。需要独立 PC 模块及带 A1/A2、RD1/RD2 的 GRF（31/32 个 Register）。");
        StringBuilder b=new StringBuilder("path,kind,role,words,encoding\n");
        for(Slot s:slots)b.append('"').append(s.path).append("\",").append(s.kind).append(',').append(s.role).append(',').append(s.count).append(',').append(s.role.equals("PC")?"PC xor "+Integer.toHexString(s.xor):"direct").append('\n');
        P3Judge.write(output.resolve("storage_map.csv"),b.toString());
    }
    static List<Integer> range(int a,int b){List<Integer> l=new ArrayList<>();while(a<b)l.add(a++);return l;}
    static Object contents(Object data)throws Exception {if(data==null)throw new P3Judge.TestError("RAM state not initialized");Method m=data.getClass().getMethod("getContents");m.setAccessible(true);return m.invoke(data);}
    static int getRegister(CircuitState s,Component c)throws Exception {Object d=s.getData(c);if(d==null)throw new P3Judge.TestError("Register state not initialized: "+c.getLocation());Method m=d.getClass().getMethod("getValue");m.setAccessible(true);return (Integer)m.invoke(d);}
    static void forceRegister(CircuitState s,Component c,int v)throws Exception {Object d=s.getData(c);Method m=d.getClass().getMethod("setValue",int.class);m.setAccessible(true);m.invoke(d,v);s.markComponentAsDirty(c);}
    static Map<String,Component> pins(Circuit c){Map<String,Component> m=new HashMap<>();for(Component x:c.getNonWires())if(x.getFactory() instanceof Pin)m.put(P3Judge.Simulator.label(x),x);return m;}
    static void input(CircuitState s,Component c,int v){Pin.FACTORY.setValue(s.getInstanceState(c),Value.createKnown(c.getEnd(0).getWidth(),v));s.markComponentAsDirty(c);}
    static int output(CircuitState s,Component c)throws Exception {Value v=s.getValue(c.getLocation());if(!v.isFullyDefined())throw new P3Judge.TestError("存储映射探针遇到未知信号 "+P3Judge.Simulator.label(c));return v.toIntValue();}
    static CircuitState isolated(P3Judge.Simulator sim,Circuit c){CircuitState s=new CircuitState(sim.project,c);for(Component p:pins(c).values())if(p.getEnd(0).isOutput())input(s,p,0);s.getPropagator().propagate();return s;}
    void scan(P3Judge.Simulator sim,Circuit circuit,List<Component> route,String path)throws Exception {
        List<Component> all=new ArrayList<>(circuit.getNonWires());all.sort(Comparator.comparing(x->x.getLocation().toString()));
        List<Component> registers=new ArrayList<>();for(Component c:all)if(c.getFactory() instanceof com.cburch.logisim.std.memory.Register)registers.add(c);
        Map<Component,Integer> mapping=new HashMap<>();Integer pcXor=null;Map<String,Component> pins=pins(circuit);
        if(registers.size()>=31&&registers.size()<=32&&pins.keySet().containsAll(Arrays.asList("A1","A2","RD1","RD2"))) {
            CircuitState probe=isolated(sim,circuit);Map<Integer,Component> markers=new HashMap<>();
            for(int i=0;i<registers.size();i++){int v=0x45120000+i+1;forceRegister(probe,registers.get(i),v);markers.put(v,registers.get(i));}probe.getPropagator().propagate();
            for(int r=0;r<32;r++) {
                input(probe,pins.get("A1"),r);input(probe,pins.get("A2"),r);probe.getPropagator().propagate();
                int a=output(probe,pins.get("RD1")),b=output(probe,pins.get("RD2"));
                if(a!=b)throw new P3Judge.TestError("GRF 两个读口对 $"+r+" 的物理寄存器映射不同");
                if(r==0&&a==0)continue;
                Component c=markers.get(a);if(c==null||mapping.put(c,r)!=null)throw new P3Judge.TestError("GRF 读口映射不是一一对应：$"+r);
            }
            for(Component c:registers)if(!mapping.containsKey(c)){if(mapping.containsValue(0))throw new P3Judge.TestError("额外未映射的 GRF 寄存器");mapping.put(c,0);}
        } else if(registers.size()==1&&pins.containsKey("PC")) {
            CircuitState probe=isolated(sim,circuit);Component r=registers.get(0);forceRegister(probe,r,0);probe.getPropagator().propagate();pcXor=output(probe,pins.get("PC"));
            for(int v:new int[]{0x1234,0x4567,0x80000000}){forceRegister(probe,r,v);probe.getPropagator().propagate();if(output(probe,pins.get("PC"))!=(v^pcXor))throw new P3Judge.TestError("PC 存储编码无法识别；支持直接 PC 或与常数异或的复位编码。");}
        }
        for(Component c:all) {
            if(c.getFactory() instanceof SubcircuitFactory) {
                List<Component> next=new ArrayList<>(route);next.add(c);scan(sim,((SubcircuitFactory)c.getFactory()).getSubcircuit(),next,path+"/"+c.getFactory().getName()+"@"+c.getLocation());continue;
            }
            String kind=c.getFactory().getName();
            if(!Arrays.asList("Register","RAM","ROM").contains(kind)) {
                if(Arrays.asList("Counter","Shift Register","D Flip-Flop","T Flip-Flop","J-K Flip-Flop","S-R Flip-Flop").contains(kind))throw new P3Judge.TestError("发现暂不支持自动映射的存储元件："+path+"/"+kind);
                continue;
            }
            Slot s=new Slot();s.component=c;s.route=new ArrayList<>(route);s.path=path+"/"+kind+"@"+c.getLocation();s.kind=kind;
            if(kind.equals("Register")) {
                if(c.getAttributeSet().getValue(StdAttr.WIDTH).getWidth()!=32)throw new P3Judge.TestError("非 32 位寄存器："+s.path);
                s.count=1;
                if(mapping.containsKey(c)){s.reg=mapping.get(c);s.role="R"+s.reg;}
                else if(pcXor!=null){s.role="PC";s.xor=pcXor;}
                else throw new P3Judge.TestError("未映射的存储元件："+s.path+"，未将其忽略为通过。");
            } else {
                CircuitState root=new CircuitState(sim.project,sim.main);root.getPropagator().propagate();
                Object memory=kind.equals("ROM")?c.getAttributeSet().getValue(Rom.CONTENTS_ATTR):contents(s.state(root).getData(c));
                HexModel model=(HexModel)memory;s.count=(int)model.getLastOffset()+1;
                if(model.getValueWidth()!=32||(kind.equals("ROM")?s.count!=4096:s.count<3072||s.count>4096))throw new P3Judge.TestError("存储器尺寸不匹配："+s.path);
                s.role=kind.equals("ROM")?"IM":"DM";
            }
            slots.add(s);
        }
    }
    int[][] capture(P3Judge.Simulator sim)throws Exception {int[][] a=new int[slots.size()][];for(int i=0;i<a.length;i++)a[i]=slots.get(i).read(sim.state);return a;}
    String compare(int[][] actual,P3Judge.Reference ref,Assembler.Program p,boolean strictZero)throws Exception {
        String first=null;
        for(int k=0;k<slots.size();k++) {
            Slot s=slots.get(k);
            for(int i=0;i<actual[k].length;i++) {
                if(s.reg==0&&!strictZero)continue;
                int want=s.role.equals("PC")?ref.pc^s.xor:s.reg>=0?ref.regs[s.reg]:s.role.equals("DM")?(i<3072?ref.memory[i]:0):(i<p.words.length?p.words[i]:0);
                P3Judge.assertions++;
                if(actual[k][i]!=want&&first==null)first=s.path+" "+s.role+(s.count>1?String.format("[%d] (byte 0x%04x)",i,i*4):"")+String.format("：期望 %08x，实际 %08x",want,actual[k][i]);
            }
        }
        return first;
    }
}
