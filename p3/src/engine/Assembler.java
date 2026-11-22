import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Small, strict assembler for the eight instructions required by this P3. */
public final class Assembler {
    public static final int BASE = 0x3000;
    public static final class Program {
        public final String name, source;
        public final int[] words;
        public final String[] lines;
        public Program(String n, String s, int[] w, String[] l) {
            name=n; source=s; words=w; lines=l;
            if(w.length==0 || w.length>4096) throw new IllegalArgumentException("Program must contain 1..4096 instruction words.");
        }
    }
    static final Map<String,Integer> REGS=new HashMap<>();
    static {
        String[] n={"zero","at","v0","v1","a0","a1","a2","a3","t0","t1","t2","t3","t4","t5","t6","t7","s0","s1","s2","s3","s4","s5","s6","s7","t8","t9","k0","k1","gp","sp","fp","ra"};
        for(int i=0;i<32;i++){REGS.put(n[i],i);REGS.put(Integer.toString(i),i);}REGS.put("s8",30);
    }
    static int reg(String s) {
        Integer r=REGS.get(s.replace("$","").toLowerCase(Locale.ROOT));
        if(r==null)throw new IllegalArgumentException("Unknown register: "+s);return r;
    }
    static long number(String s) {
        s=s.trim().replace("_","");boolean neg=s.startsWith("-");
        if(s.startsWith("-")||s.startsWith("+"))s=s.substring(1);
        int radix=10;
        if(s.startsWith("0x")||s.startsWith("0X")){radix=16;s=s.substring(2);}
        else if(s.startsWith("0b")||s.startsWith("0B")){radix=2;s=s.substring(2);}
        long v=Long.parseLong(s,radix);return neg?-v:v;
    }
    static int imm16(String s, boolean unsigned) {
        long v=number(s);
        if(v<(unsigned?0:-32768)||v>65535)throw new IllegalArgumentException("16-bit immediate out of range: "+s);
        if(!unsigned&&v>32767&&!s.toLowerCase(Locale.ROOT).contains("0x")&&!s.toLowerCase(Locale.ROOT).contains("0b"))
            throw new IllegalArgumentException("Signed decimal offset must be -32768..32767: "+s);
        return (int)v&0xffff;
    }
    static String clean(String s) {
        int a=s.indexOf('#'),b=s.indexOf("//");int end=s.length();
        if(a>=0)end=Math.min(end,a);if(b>=0)end=Math.min(end,b);
        return s.substring(0,end).replace("\ufeff","").trim();
    }
    public static Program assemble(String name,String source) {
        List<String> instructions=new ArrayList<>();List<Integer> lineNos=new ArrayList<>();
        Map<String,Integer> labels=new HashMap<>();String[] input=source.split("\\r?\\n",-1);
        for(int n=0;n<input.length;n++) {
            String s=clean(input[n]);
            while(s.contains(":")) {
                int k=s.indexOf(':');String l=s.substring(0,k).trim();
                if(!l.matches("[A-Za-z_.$][A-Za-z0-9_.$]*")||labels.put(l,instructions.size())!=null)
                    throw new IllegalArgumentException("Line "+(n+1)+": invalid or duplicate label "+l);
                s=s.substring(k+1).trim();
            }
            if(s.isEmpty())continue;
            if(s.startsWith(".text")) {
                String[] p=s.split("\\s+");
                if(p.length>2 || (p.length==2&&number(p[1])!=BASE))throw new IllegalArgumentException(".text must start at 0x3000");
                continue;
            }
            if(s.startsWith(".globl ")||s.startsWith(".global ")||s.equals(".set noreorder"))continue;
            if(s.startsWith(".word")) {
                String[] ws=s.substring(5).trim().split("[\\s,]+");
                for(String w:ws){instructions.add(".word "+w);lineNos.add(n+1);}continue;
            }
            if(s.startsWith("."))throw new IllegalArgumentException("Line "+(n+1)+": unsupported directive "+s+"; initialize memory with sw.");
            instructions.add(s);lineNos.add(n+1);
        }
        int[] words=new int[instructions.size()];String[] lines=new String[words.length];
        for(int n=0;n<words.length;n++) {
            String s=instructions.get(n);String[] t=s.replace(","," ").replace("("," ").replace(")"," ").trim().split("\\s+");
            String op=t[0].toLowerCase(Locale.ROOT);
            try {
                if(op.equals("nop")&&t.length==1)words[n]=0;
                else if((op.equals("add")||op.equals("sub"))&&t.length==4)
                    words[n]=(reg(t[2])<<21)|(reg(t[3])<<16)|(reg(t[1])<<11)|(op.equals("add")?32:34);
                else if(op.equals("ori")&&t.length==4)
                    words[n]=(13<<26)|(reg(t[2])<<21)|(reg(t[1])<<16)|imm16(t[3],true);
                else if(op.equals("lui")&&t.length==3)
                    words[n]=(15<<26)|(reg(t[1])<<16)|imm16(t[2],true);
                else if((op.equals("lw")||op.equals("sw"))&&t.length==4)
                    words[n]=((op.equals("lw")?35:43)<<26)|(reg(t[3])<<21)|(reg(t[1])<<16)|imm16(t[2],false);
                else if(op.equals("beq")&&t.length==4) {
                    Integer target=labels.get(t[3]);int offset;
                    if(target!=null){offset=target-(n+1);if(offset<-32768||offset>32767)throw new IllegalArgumentException("Branch target too far");}
                    else offset=imm16(t[3],false);
                    words[n]=(4<<26)|(reg(t[1])<<21)|(reg(t[2])<<16)|(offset&65535);
                } else if(op.equals(".word")&&t.length==2) {
                    long v=number(t[1]);if(v<Integer.MIN_VALUE||v>0xffffffffL)throw new IllegalArgumentException("Word out of range");words[n]=(int)v;
                } else throw new IllegalArgumentException("Unsupported instruction or operands; supported: add sub ori lw sw beq lui nop");
                lines[n]="line "+lineNos.get(n)+": "+s;
            } catch(RuntimeException e) {throw new IllegalArgumentException("Line "+lineNos.get(n)+" ["+s+"]: "+e.getMessage(),e);}
        }
        return new Program(name,source,words,lines);
    }
    public static Program read(Path path)throws IOException {
        String s=new String(Files.readAllBytes(path),StandardCharsets.UTF_8).replace("\ufeff","");
        boolean hex=path.toString().toLowerCase(Locale.ROOT).endsWith(".hex") || s.trim().startsWith("v2.0 raw");
        if(!hex) {
            String first="";for(String l:s.split("\\r?\\n"))if(!clean(l).isEmpty()){first=clean(l);break;}
            hex=first.matches("(?:[0-9]+\\*)?[0-9a-fA-F]{8}(?:\\s+(?:[0-9]+\\*)?[0-9a-fA-F]{8})*");
        }
        if(!hex)return assemble(path.getFileName().toString(),s);
        List<Integer> ws=new ArrayList<>();
        for(String line:s.split("\\r?\\n")) {
            line=clean(line);if(line.isEmpty()||line.equals("v2.0 raw"))continue;
            for(String token:line.split("\\s+")) {
                String[] p=token.split("\\*");int count=p.length==2?Integer.parseInt(p[0]):1;String w=p[p.length-1];
                if(p.length>2||count<1||count>4096||!w.matches("[0-9a-fA-F]{1,8}"))throw new IllegalArgumentException("Invalid hex token: "+token);
                if(ws.size()+count>4096)throw new IllegalArgumentException("ROM image exceeds 4096 words");
                for(int k=0;k<count;k++)ws.add((int)Long.parseLong(w,16));
            }
        }
        int[] w=new int[ws.size()];String[] l=new String[w.length];StringBuilder asm=new StringBuilder(".text 0x3000\n");
        for(int n=0;n<w.length;n++){w[n]=ws.get(n);l[n]="word "+n+": "+disasm(w[n]);asm.append(String.format(".word 0x%08x # %s%n",w[n],disasm(w[n])));}
        return new Program(path.getFileName().toString(),asm.toString(),w,l);
    }
    public static String disasm(int w) {
        int op=w>>>26,rs=(w>>>21)&31,rt=(w>>>16)&31,rd=(w>>>11)&31;
        if(w==0)return "nop";
        if(op==0&&((w&63)==32||(w&63)==34))return String.format("%s $%d, $%d, $%d",(w&63)==32?"add":"sub",rd,rs,rt);
        if(op==13)return String.format("ori $%d, $%d, 0x%04x",rt,rs,w&65535);
        if(op==15)return String.format("lui $%d, 0x%04x",rt,w&65535);
        if(op==35||op==43)return String.format("%s $%d, %d($%d)",op==35?"lw":"sw",rt,(int)(short)w,rs);
        if(op==4)return String.format("beq $%d, $%d, %d",rs,rt,(int)(short)w);
        return String.format("unsupported 0x%08x",w);
    }
}
