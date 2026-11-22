import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

/** Lossless delta snapshots: every storage value is recoverable for every sample. */
final class TraceArchive implements Closeable {
    final DataOutputStream out;final PrintWriter csv;final StorageLayout layout;
    int[][] previous;int[] previousMem=new int[3072],previousROM=new int[4096];int samples;
    TraceArchive(Path dir,StorageLayout l)throws Exception {
        layout=l;previous=new int[l.slots.size()][];
        out=new DataOutputStream(new BufferedOutputStream(new GZIPOutputStream(Files.newOutputStream(dir.resolve("state.p3trace.gz")))));
        out.writeUTF("P3TRACE3");out.writeInt(l.slots.size());
        for(int i=0;i<l.slots.size();i++){StorageLayout.Slot s=l.slots.get(i);out.writeUTF(s.path);out.writeUTF(s.role);out.writeInt(s.xor);out.writeInt(s.count);previous[i]=new int[s.count];}
        csv=new PrintWriter(Files.newBufferedWriter(dir.resolve("signals.csv"),StandardCharsets.UTF_8));
        P3Judge.csv(csv,new String[]{"sample","phase","cycle","event","clk","reset","executed_pc","executed_word","Instr","pc","RegWrite","RegAddr","RegData","MemWrite","MemAddr","MemData"});
    }
    static void delta(DataOutputStream out,int[] a,int[] old)throws IOException {int n=0;for(int i=0;i<a.length;i++)if(a[i]!=old[i])n++;out.writeInt(n);for(int i=0;i<a.length;i++)if(a[i]!=old[i]){out.writeInt(i);out.writeInt(a[i]);old[i]=a[i];}}
    int sample(P3Judge.Simulator sim,String phase,int cycle,String event,int pc,int word,P3Judge.Reference ref,int[][] actual,Assembler.Program program)throws Exception {
        int id=++samples;out.writeInt(id);out.writeUTF(phase);out.writeInt(cycle);out.writeUTF(event);out.writeInt(pc);out.writeInt(word);
        int clk=sim.state.getValue(sim.clock.getLocation()).toIntValue(),reset=sim.known("reset");out.writeInt(clk);out.writeInt(reset);
        String[] row=new String[16];row[0]=""+id;row[1]=phase;row[2]=""+cycle;row[3]=event;row[4]=""+clk;row[5]=""+reset;row[6]=String.format("%08x",pc);row[7]=String.format("%08x",word);
        for(int i=0;i<8;i++){String v=sim.value(P3Judge.SIGNALS[i]).toHexString();out.writeUTF(v);row[8+i]=v;}P3Judge.csv(csv,row);
        out.writeInt(ref.pc);for(int r:ref.regs)out.writeInt(r);delta(out,ref.memory,previousMem);delta(out,Arrays.copyOf(program.words,4096),previousROM);
        for(int k=0;k<actual.length;k++)delta(out,actual[k],previous[k]);
        return id;
    }
    public void close()throws IOException {try{out.close();}finally{csv.close();}}
    static final class Snapshot {
        int sample,cycle,pc,word,clk,reset,expectedPC;String phase,event;String[] signals,paths,roles;int[] xors,regs,memory,rom;int[][] actual;
        String csv(){StringWriter sw=new StringWriter();PrintWriter w=new PrintWriter(sw);P3Judge.csv(w,new String[]{"path","index","expected","actual","note"});
            P3Judge.csv(w,new String[]{"sample",""+sample,"",phase+" / cycle="+cycle+" / "+event,"clk="+clk+" reset="+reset});
            for(int i=0;i<8;i++)P3Judge.csv(w,new String[]{"main/"+P3Judge.SIGNALS[i],"","see signals.csv and expectations.csv",signals[i],"pre_edge checks instruction intent; post_edge already shows next instruction"});
            for(int k=0;k<paths.length;k++)for(int i=0;i<actual[k].length;i++){
                String role=roles[k];String expected;int v;
                if(role.equals("IM")){expected=rom==null?"program.hex":String.format("%08x",rom[i]);}else{v=role.equals("PC")?expectedPC^xors[k]:role.equals("DM")?(i<3072?memory[i]:0):regs[Integer.parseInt(role.substring(1))];expected=String.format("%08x",v);}
                P3Judge.csv(w,new String[]{paths[k],""+i,expected,String.format("%08x",actual[k][i]),role});
            }w.flush();return sw.toString();}
    }
    static void readDelta(DataInputStream d,int[] v)throws IOException {int n=d.readInt();if(n<0||n>v.length)throw new IOException("Invalid trace delta");while(n-->0){int i=d.readInt();if(i<0||i>=v.length)throw new IOException("Invalid trace address");v[i]=d.readInt();}}
    static Snapshot read(Path file,int target)throws Exception {
        try(DataInputStream d=new DataInputStream(new BufferedInputStream(new GZIPInputStream(Files.newInputStream(file))))) {
            String magic=d.readUTF();boolean v3=magic.equals("P3TRACE3");if(!v3&&!magic.equals("P3TRACE2"))throw new IOException("Unsupported trace version");Snapshot s=new Snapshot();int n=d.readInt();if(n<1||n>1000)throw new IOException("Invalid storage count");if(v3)s.rom=new int[4096];
            s.paths=new String[n];s.roles=new String[n];s.xors=new int[n];s.actual=new int[n][];s.regs=new int[32];s.memory=new int[3072];s.signals=new String[8];
            for(int i=0;i<n;i++){s.paths[i]=d.readUTF();s.roles[i]=d.readUTF();s.xors[i]=d.readInt();int size=d.readInt();if(size<1||size>65536)throw new IOException("Invalid storage size");s.actual[i]=new int[size];}
            while(true){try{s.sample=d.readInt();}catch(EOFException end){throw new IOException("样本编号超出范围；此文件共有 "+s.sample+" 个样本");}
                s.phase=d.readUTF();s.cycle=d.readInt();s.event=d.readUTF();s.pc=d.readInt();s.word=d.readInt();s.clk=d.readInt();s.reset=d.readInt();for(int i=0;i<8;i++)s.signals[i]=d.readUTF();
                s.expectedPC=d.readInt();for(int i=0;i<32;i++)s.regs[i]=d.readInt();readDelta(d,s.memory);if(v3)readDelta(d,s.rom);for(int[] a:s.actual)readDelta(d,a);
                if(s.sample==target)return s;
            }
        }
    }
}
