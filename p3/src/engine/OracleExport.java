import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.io.*;
/** Export the actual judge reference state for independent MARS validation. */
public final class OracleExport {
    public static void main(String[] args)throws Exception {
        Assembler.Program p=Assembler.read(Paths.get(args[0]));P3Judge.Reference r=new P3Judge.Reference();
        int count=0;
        while(true) {
            int i=(r.pc-0x3000)/4;
            if(i<0||i>=p.words.length||++count>50000)throw new IllegalArgumentException("reference program did not terminate");
            P3Judge.Expected e=r.decode(p.words[i]);r.commit(e);
            if(r.pc==0x3000+p.words.length*4||(i==p.words.length-1&&e.instruction.equals("beq")&&e.next==e.pc))break;
        }
        try(PrintWriter out=new PrintWriter(Files.newBufferedWriter(Paths.get(args[1]),StandardCharsets.UTF_8))) {
            out.println("cycles="+count);for(int i=0;i<32;i++)out.printf("R%d=%08x%n",i,r.regs[i]);
            for(int i=0;i<3072;i++)out.printf("M%04x=%08x%n",i*4,r.memory[i]);
        }
    }
}
