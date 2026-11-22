import java.nio.file.*;
import java.util.concurrent.atomic.*;
import javax.swing.*;

/** Headless integration test of the same Swing start action used by the launcher. */
public class AppSmoke {
    public static void main(String[] args)throws Exception {
        System.setProperty("java.awt.headless","true");System.setProperty("java.util.prefs.PreferencesFactory","MemoryPreferencesFactory");
        final String mode=args.length>2?args[2]:"manual";final int expectedRows=mode.equals("auto")?29:4;
        final AtomicReference<JudgeApp> ref=new AtomicReference<>();
        SwingUtilities.invokeAndWait(()->{JudgeApp a=new JudgeApp(Paths.get(args[0]));a.circuit.setText(args[1]);a.mode.setSelectedIndex(mode.equals("manual")?1:0);a.count.setValue(mode.equals("cancel")?100:1);a.strict.setSelected(mode.equals("manual"));a.editor.setText(JudgeApp.SAMPLE);ref.set(a);a.start.doClick();});
        JudgeApp app=ref.get();AtomicBoolean finished=new AtomicBoolean();
        if(mode.equals("cancel")){Thread.sleep(300);SwingUtilities.invokeAndWait(()->app.stop.doClick());}
        for(int n=0;n<600;n++){Thread.sleep(100);SwingUtilities.invokeAndWait(()->finished.set(app.start.isEnabled()));if(finished.get())break;}
        if(!finished.get()){if(app.running!=null)app.running.destroyForcibly();throw new AssertionError("GUI start workflow timed out");}
        if(mode.equals("cancel")){SwingUtilities.invokeAndWait(()->{if(!app.status.getText().contains("已停止"))throw new AssertionError("Cancellation reported incorrectly: "+app.status.getText());});System.out.println("UI CANCEL PASS");System.exit(0);}
        SwingUtilities.invokeAndWait(()->{if(app.model.getRowCount()!=expectedRows)throw new AssertionError("Expected "+expectedRows+" cases; got "+app.model.getRowCount()+" log="+app.log.getText());for(int i=0;i<expectedRows;i++)if(!app.model.getValueAt(i,0).equals("PASS"))throw new AssertionError("GUI workflow failed: "+app.log.getText());if(!app.report.isEnabled())throw new AssertionError("Report button disabled");System.out.println("UI WORKFLOW PASS: "+mode+" -> runner -> "+expectedRows+" PASS rows -> report enabled\n"+app.lastOutput);});
        Path trace=app.caseDirs.get(0).resolve("state.p3trace.gz");TraceArchive.Snapshot s=TraceArchive.read(trace,1);if(s.actual.length!=35||s.expectedPC!=0x3000||s.rom[0]!=(mode.equals("manual")?0x3c081234:0x34080004))throw new AssertionError("Trace round trip");
        java.util.List<String> lines=Files.readAllLines(app.caseDirs.get(0).resolve("signals.csv"));int last=Integer.parseInt(lines.get(lines.size()-1).split(",")[0].replace("\"",""));s=TraceArchive.read(trace,last);
        if(mode.equals("manual")&&(s.memory[0]!=0x12345678||s.regs[8]!=0x12345678||s.regs[11]!=0xbeef))throw new AssertionError("Final trace delta reconstruction");
        P3Judge.write(app.lastOutput.resolve("snapshot_roundtrip.csv"),s.csv());System.out.println("TRACE ROUNDTRIP PASS");System.exit(0);
    }
}
