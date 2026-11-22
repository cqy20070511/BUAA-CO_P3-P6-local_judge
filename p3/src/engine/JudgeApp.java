import java.awt.*;
import java.awt.datatransfer.DataFlavor;
import java.awt.event.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.List;
import javax.imageio.ImageIO;
import javax.swing.*;
import javax.swing.border.EmptyBorder;
import javax.swing.filechooser.FileNameExtensionFilter;
import javax.swing.table.DefaultTableModel;

public final class JudgeApp extends JPanel {
    final Path home;final JTextField circuit=new JTextField();final JSpinner count=new JSpinner(new SpinnerNumberModel(12,0,10000,1)),seed=new JSpinner(new SpinnerNumberModel((Number)Long.valueOf(20261028L),Long.valueOf(0L),Long.valueOf(Long.MAX_VALUE),(Number)Long.valueOf(1L)));
    final JCheckBox full=new JCheckBox("遍历全部 3072 个数据字并复位"),strict=new JCheckBox("严格检查物理 $0 恒为 0",true),resets=new JCheckBox("低电平 / 高电平 / 跨上升沿复位",true);
    final JSpinner maxCycles=new JSpinner(new SpinnerNumberModel(50000,1,10000000,1000)),timeout=new JSpinner(new SpinnerNumberModel(900,10,86400,60));
    final JTextArea editor=new JTextArea(),log=new JTextArea(),detail=new JTextArea();final JTabbedPane mode=new JTabbedPane();
    final JButton start=new JButton("开始自动测试"),stop=new JButton("停止"),report=new JButton("打开完整报告"),folder=new JButton("结果文件夹"),state=new JButton("查看周期状态"),logisim=new JButton("用 Logisim 打开用例");
    final JLabel status=new JLabel("选择 CPU.circ，然后选择测试方式。"),pathStatus=new JLabel(" ");final JProgressBar progress=new JProgressBar();
    final DefaultTableModel model=new DefaultTableModel(new String[]{"结果","用例","周期","错误位置 / 说明"},0){public boolean isCellEditable(int r,int c){return false;}};
    final JTable table=new JTable(model);final List<Path> caseDirs=new ArrayList<>();volatile Process running;volatile boolean cancelled;Path lastOutput;final List<JComponent> lockable=new ArrayList<>();
    static final String SAMPLE=".text 0x3000\n# 支持 add sub ori lw sw beq lui nop，无延迟槽\nlui $t0, 0x1234\nori $t0, $t0, 0x5678\nsw $t0, 0($0)\nlw $t1, 0($0)\nsub $t2, $t0, $t1\nbeq $t2, $0, equal\nori $t3, $0, 0xdead\nequal: ori $t3, $0, 0xbeef\nnop\nfinish: beq $0, $0, finish\n";
    JudgeApp(Path home) {
        this.home=home;setLayout(new BorderLayout(0,12));setBorder(new EmptyBorder(18,22,18,22));setBackground(new Color(245,247,251));
        JPanel header=new JPanel(new BorderLayout(0,8));header.setOpaque(false);JLabel title=new JLabel("P3  CPU 自动评测");title.setFont(title.getFont().deriveFont(Font.BOLD,25f));header.add(title,BorderLayout.NORTH);
        JPanel pick=new JPanel(new BorderLayout(8,0));pick.add(new JLabel("电路文件"),BorderLayout.WEST);pick.add(circuit,BorderLayout.CENTER);JButton browse=new JButton("选择 .circ");browse.addActionListener(e->chooseCircuit());pick.add(browse,BorderLayout.EAST);header.add(pick,BorderLayout.CENTER);
        header.add(new JLabel("MARS 期望结果  →  ROM 导入  →  Logisim 仿真  →  信号与内部状态逐周期比较"),BorderLayout.SOUTH);add(header,BorderLayout.NORTH);
        circuit.setTransferHandler(new TransferHandler(){public boolean canImport(TransferSupport s){return s.isDataFlavorSupported(DataFlavor.javaFileListFlavor);}public boolean importData(TransferSupport s){try{List<?> fs=(List<?>)s.getTransferable().getTransferData(DataFlavor.javaFileListFlavor);if(!fs.isEmpty()){circuit.setText(((File)fs.get(0)).getAbsolutePath());return true;}}catch(Exception ignored){}return false;}});
        JPanel automatic=new JPanel();automatic.setLayout(new BoxLayout(automatic,BoxLayout.Y_AXIS));automatic.setBorder(new EmptyBorder(12,12,12,12));
        automatic.add(new JLabel("自动运行 25 组定向测试，并按种子生成随机程序。"));automatic.add(Box.createVerticalStrut(8));automatic.add(row(new JLabel("随机用例数"),count,new JLabel("随机种子"),seed));automatic.add(row(full));
        JTextArea description=new JTextArea("覆盖算术边界、立即数扩展、$0、寄存器编号、正负访存偏移、六种 beq 行为、ROM 末地址。\n每个随机程序先初始化寄存器，再混合执行八条指令；访存地址始终对齐且在 0x0000–0x2fff。\n\n也可以生成一个随机程序到右侧编辑页，查看、修改后单独测试。");description.setEditable(false);description.setLineWrap(true);description.setWrapStyleWord(true);description.setOpaque(false);automatic.add(description);
        JButton generate=new JButton("生成一个程序 → 手写汇编页");generate.addActionListener(e->{TestSuite.Case c=TestSuite.random(0,((Number)seed.getValue()).longValue());editor.setText(c.program.source);mode.setSelectedIndex(1);});automatic.add(row(generate));mode.addTab("自动生成测试",automatic);
        JPanel manual=new JPanel(new BorderLayout(0,6));JButton load=new JButton("导入 .asm"),save=new JButton("保存汇编"),machine=new JButton("检查 / 导出机器码");load.addActionListener(e->loadCode());save.addActionListener(e->saveCode());machine.addActionListener(e->machine());manual.add(row(load,save,machine,new JLabel("不支持 syscall、addi、j、伪指令和 .data")),BorderLayout.NORTH);
        editor.setFont(new Font(Font.MONOSPACED,Font.PLAIN,14));editor.setText(SAMPLE);JScrollPane es=new JScrollPane(editor);es.setRowHeaderView(new LineNumbers(editor));manual.add(es);mode.addTab("手写 / 导入汇编",manual);
        JPanel upper=new JPanel(new BorderLayout(0,6));upper.setMinimumSize(new Dimension(600,300));upper.setPreferredSize(new Dimension(1100,420));upper.add(mode);JPanel opts=new JPanel();opts.setLayout(new BoxLayout(opts,BoxLayout.Y_AXIS));opts.add(row(resets,strict));opts.add(row(new JLabel("单阶段周期上限"),maxCycles,new JLabel("总时限（秒）"),timeout));upper.add(opts,BorderLayout.SOUTH);
        strict.setToolTipText("开启：物理 R0 内容必须为 0；关闭：完整记录 R0，但只判断读取 $0 的架构行为。");
        table.setRowHeight(25);table.getColumnModel().getColumn(0).setMaxWidth(90);table.getColumnModel().getColumn(2).setMaxWidth(80);table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        table.getSelectionModel().addListSelectionListener(e->{int r=table.getSelectedRow();if(r>=0&&r<caseDirs.size())try{Path f=caseDirs.get(r).resolve("failure.txt");detail.setText(Files.exists(f)?new String(Files.readAllBytes(f),StandardCharsets.UTF_8):"PASS\n"+caseDirs.get(r));}catch(Exception ex){detail.setText(ex.toString());}});
        log.setEditable(false);log.setFont(new Font(Font.MONOSPACED,Font.PLAIN,12));detail.setEditable(false);detail.setLineWrap(true);detail.setWrapStyleWord(true);
        JScrollPane resultScroll=new JScrollPane(table);resultScroll.setColumnHeaderView(table.getTableHeader());table.setFillsViewportHeight(true);JTabbedPane outputs=new JTabbedPane();outputs.setMinimumSize(new Dimension(600,150));outputs.setPreferredSize(new Dimension(1100,220));outputs.addTab("测试结果",resultScroll);outputs.addTab("运行日志",new JScrollPane(log));outputs.addTab("错误详情",new JScrollPane(detail));
        JSplitPane split=new JSplitPane(JSplitPane.VERTICAL_SPLIT,upper,outputs);split.setResizeWeight(.60);split.setDividerLocation(420);split.setBorder(null);add(split,BorderLayout.CENTER);
        JPanel footer=new JPanel(new BorderLayout(0,8));footer.setOpaque(false);JPanel buttons=row(start,stop,report,folder,state,logisim);footer.add(buttons,BorderLayout.NORTH);
        JPanel info=new JPanel(new BorderLayout(8,0));info.add(status);progress.setPreferredSize(new Dimension(150,18));info.add(progress,BorderLayout.EAST);footer.add(info,BorderLayout.CENTER);footer.add(pathStatus,BorderLayout.SOUTH);add(footer,BorderLayout.SOUTH);
        start.addActionListener(e->start());stop.addActionListener(e->{cancelled=true;Process p=running;if(p!=null)p.destroyForcibly();status.setText("正在停止；未完成的测试不会标为通过。");});
        report.addActionListener(e->open(lastOutput.resolve("report.html")));folder.addActionListener(e->open(lastOutput));state.addActionListener(e->trace());logisim.addActionListener(e->openLogisim());
        stop.setEnabled(false);report.setEnabled(false);folder.setEnabled(false);state.setEnabled(false);logisim.setEnabled(false);
        Collections.addAll(lockable,circuit,browse,count,seed,full,strict,resets,maxCycles,timeout,editor,generate,load,save,machine);
        Path settings=home.resolve("last_circuit.txt");try{if(Files.exists(settings))circuit.setText(new String(Files.readAllBytes(settings),StandardCharsets.UTF_8));}catch(Exception ignored){}
    }
    static JPanel row(Component...cs){JPanel p=new JPanel(new FlowLayout(FlowLayout.LEFT,8,4));for(Component c:cs)p.add(c);return p;}
    static final class LineNumbers extends JComponent {
        final JTextArea a;LineNumbers(JTextArea a){this.a=a;a.getDocument().addDocumentListener(new javax.swing.event.DocumentListener(){public void insertUpdate(javax.swing.event.DocumentEvent e){revalidate();repaint();}public void removeUpdate(javax.swing.event.DocumentEvent e){revalidate();repaint();}public void changedUpdate(javax.swing.event.DocumentEvent e){repaint();}});}
        public Dimension getPreferredSize(){return new Dimension(54,a.getPreferredSize().height);}
        protected void paintComponent(Graphics g){g.setColor(new Color(239,242,247));g.fillRect(0,0,getWidth(),getHeight());g.setColor(Color.GRAY);g.setFont(a.getFont());FontMetrics f=g.getFontMetrics();for(int i=0;i<a.getLineCount();i++)g.drawString(""+(i+1),8,(i+1)*f.getHeight()-f.getDescent());}
    }
    JFileChooser chooser(String title,String ext){JFileChooser f=new JFileChooser(home.toFile());f.setDialogTitle(title);f.setFileFilter(new FileNameExtensionFilter(ext+" files",ext));return f;}
    void chooseCircuit(){JFileChooser f=chooser("选择 CPU 电路","circ");if(f.showOpenDialog(this)==JFileChooser.APPROVE_OPTION)circuit.setText(f.getSelectedFile().getAbsolutePath());}
    void loadCode(){JFileChooser f=chooser("导入 MIPS 汇编","asm");if(f.showOpenDialog(this)==JFileChooser.APPROVE_OPTION)try{editor.setText(new String(Files.readAllBytes(f.getSelectedFile().toPath()),StandardCharsets.UTF_8));}catch(Exception ex){error(ex);}}
    void saveCode(){JFileChooser f=chooser("保存汇编","asm");if(f.showSaveDialog(this)==JFileChooser.APPROVE_OPTION)try{Files.write(f.getSelectedFile().toPath(),editor.getText().getBytes(StandardCharsets.UTF_8));}catch(Exception ex){error(ex);}}
    Path newOutput(String prefix)throws Exception{Path p=home.resolve("results").resolve(prefix+LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss_SSS")));Files.createDirectories(p);return p;}
    void machine(){try{Assembler.Program p=Assembler.assemble("editor",editor.getText());Path dir=newOutput("code_");P3Judge.artifacts(dir,p,"program");JTextArea view=new JTextArea(new String(Files.readAllBytes(dir.resolve("program.listing.txt")),StandardCharsets.UTF_8));view.setEditable(false);view.setFont(new Font(Font.MONOSPACED,Font.PLAIN,13));JScrollPane scroll=new JScrollPane(view);scroll.setPreferredSize(new Dimension(960,480));JOptionPane.showMessageDialog(this,scroll,"机器码已导出到 "+dir,JOptionPane.PLAIN_MESSAGE);}catch(Exception ex){error(ex);}}
    List<String> javaCommand(String clazz){List<String> c=new ArrayList<>();c.add(Paths.get(System.getProperty("java.home"),"bin","java.exe").toString());c.add("-Dfile.encoding=UTF-8");c.add("-Xmx768m");c.add("-cp");c.add(home.resolve("p3judge.jar")+File.pathSeparator+home.resolve("lib")+File.separator+"*");c.add(clazz);return c;}
    void start(){try {
        Path cpu=Paths.get(circuit.getText().trim()).toAbsolutePath();if(!Files.isRegularFile(cpu))throw new IOException("请选择已保存的 CPU.circ 文件。");
        final boolean manual=mode.getSelectedIndex()==1;if(manual)Assembler.assemble("editor",editor.getText());lastOutput=newOutput("run_");final Path out=lastOutput;
        Files.write(home.resolve("last_circuit.txt"),cpu.toString().getBytes(StandardCharsets.UTF_8));List<String> cmd=javaCommand("AutomationRunner");Collections.addAll(cmd,"--circuit",cpu.toString(),"--out",out.toString(),"--random",count.getValue().toString(),"--seed",Long.toString(((Number)seed.getValue()).longValue()),"--max-cycles",maxCycles.getValue().toString(),"--timeout",timeout.getValue().toString());
        if(manual){Path code=out.resolve("input.asm");Files.write(code,editor.getText().getBytes(StandardCharsets.UTF_8));Collections.addAll(cmd,"--program",code.toString());}
        if(full.isSelected())cmd.add("--full-memory");if(!strict.isSelected())cmd.add("--architectural-zero");if(!resets.isSelected())cmd.add("--no-reset-matrix");
        model.setRowCount(0);caseDirs.clear();log.setText("");detail.setText("");cancelled=false;setRunning(true);status.setText("正在汇编、生成期望并运行 Logisim 仿真…");pathStatus.setText(out.toString());
        new SwingWorker<Integer,String>() {
            protected Integer doInBackground()throws Exception {running=new ProcessBuilder(cmd).directory(home.toFile()).redirectErrorStream(true).start();if(cancelled)running.destroyForcibly();try(BufferedReader reader=new BufferedReader(new InputStreamReader(running.getInputStream(),StandardCharsets.UTF_8));BufferedWriter file=Files.newBufferedWriter(out.resolve("run.log"),StandardCharsets.UTF_8)){String line;while((line=reader.readLine())!=null){publish(line);file.write(line);file.newLine();}}return running.waitFor();}
            protected void process(List<String> lines){for(String line:lines){log.append(line+"\n");if(line.startsWith("["))status.setText(line);}log.setCaretPosition(log.getDocument().getLength());}
            protected void done(){running=null;setRunning(false);try{int code=get();status.setText(cancelled?"已停止：测试结果不完整。":code==0?"测试完成：全部通过。":code==1?"测试完成：发现电路不一致，请查看错误详情。":"测试未全部完成 / 输入或环境错误，请查看日志。");if(cancelled)P3Judge.write(out.resolve("CANCELLED.txt"),"用户停止测试；结果不完整，不代表通过。\n");populate(out);}catch(Exception ex){status.setText(cancelled?"已停止：测试结果不完整。":"运行失败："+ex.getMessage());if(!cancelled)error(ex);}report.setEnabled(Files.exists(out.resolve("report.html")));folder.setEnabled(true);state.setEnabled(true);logisim.setEnabled(!caseDirs.isEmpty());}
        }.execute();
    }catch(Exception ex){error(ex);}}
    void setRunning(boolean on){start.setEnabled(!on);stop.setEnabled(on);progress.setIndeterminate(on);for(JComponent c:lockable)c.setEnabled(!on);if(on){report.setEnabled(false);folder.setEnabled(false);state.setEnabled(false);logisim.setEnabled(false);}}
    void populate(Path out)throws Exception{Path tsv=out.resolve("results.tsv");if(!Files.exists(tsv))return;for(String line:Files.readAllLines(tsv,StandardCharsets.UTF_8)){String[] a=line.split("\t",-1);if(a.length>=5){model.addRow(new Object[]{a[0],a[1],a[2],a[3]});caseDirs.add(out.resolve(a[4]));}}if(model.getRowCount()>0){int selected=0;for(int i=0;i<model.getRowCount();i++)if(!model.getValueAt(i,0).equals("PASS")){selected=i;break;}table.setRowSelectionInterval(selected,selected);}}
    Path selectedCase(){int n=table.getSelectedRow();return n>=0&&n<caseDirs.size()?caseDirs.get(n):null;}
    void trace(){try{Path c=selectedCase();JFileChooser f=new JFileChooser((c!=null?c:lastOutput!=null?lastOutput:home).toFile());f.setDialogTitle("选择 state.p3trace.gz（signals.csv 中可查样本编号）");if(c!=null)f.setSelectedFile(c.resolve("state.p3trace.gz").toFile());if(f.showOpenDialog(this)!=JFileChooser.APPROVE_OPTION)return;String value=JOptionPane.showInputDialog(this,"要查看的样本编号（从 1 开始，失败报告中会列出）","1");if(value==null)return;int id=Integer.parseInt(value);TraceArchive.Snapshot s=TraceArchive.read(f.getSelectedFile().toPath(),id);Path csv=f.getSelectedFile().toPath().getParent().resolve("snapshot_"+id+".csv");P3Judge.write(csv,s.csv());JTextArea text=new JTextArea(s.csv());text.setEditable(false);text.setFont(new Font(Font.MONOSPACED,Font.PLAIN,12));JScrollPane view=new JScrollPane(text);view.setPreferredSize(new Dimension(1000,550));JOptionPane.showMessageDialog(this,view,"样本 "+id+" / "+s.phase+" / cycle "+s.cycle+" / "+s.event+"（已导出 CSV）",JOptionPane.PLAIN_MESSAGE);}catch(Exception ex){error(ex);}}
    void openLogisim(){try{Path c=selectedCase();if(c==null)throw new IOException("请先选择一个用例。");List<String> cmd=new ArrayList<>();cmd.add(Paths.get(System.getProperty("java.home"),"bin","javaw.exe").toString());cmd.add("-Djava.util.prefs.PreferencesFactory=MemoryPreferencesFactory");cmd.add("-cp");cmd.add(home.resolve("p3judge.jar")+File.pathSeparator+home.resolve("lib/logisim-2.7.1.jar"));cmd.add("com.cburch.logisim.Main");cmd.add(c.resolve("CPU_loaded.circ").toString());new ProcessBuilder(cmd).directory(home.toFile()).start();}catch(Exception ex){error(ex);}}
    void open(Path p){try{if(!Files.exists(p))throw new IOException("文件尚未生成："+p);Desktop.getDesktop().open(p.toFile());}catch(Exception ex){error(ex);}}
    void error(Exception ex){if(GraphicsEnvironment.isHeadless())throw new RuntimeException(ex);JOptionPane.showMessageDialog(this,ex.getMessage(),"请检查",JOptionPane.ERROR_MESSAGE);}
    static void layoutTree(Container c){c.doLayout();for(Component child:c.getComponents())if(child instanceof Container)layoutTree((Container)child);}
    public static void main(String[] args)throws Exception {
        System.setProperty("java.util.prefs.PreferencesFactory","MemoryPreferencesFactory");UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());Font font=new Font("Microsoft YaHei UI",Font.PLAIN,13);for(Object k:Collections.list(UIManager.getDefaults().keys()))if(UIManager.get(k) instanceof javax.swing.plaf.FontUIResource)UIManager.put(k,new javax.swing.plaf.FontUIResource(font));
        Path home=Paths.get(JudgeApp.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toAbsolutePath();home=Files.isDirectory(home)?home.getParent():home.getParent();final Path base=home;
        if(args.length>0&&args[0].equals("--render")){JudgeApp app=new JudgeApp(base);app.setSize(1200,900);layoutTree(app);BufferedImage im=new BufferedImage(1200,900,BufferedImage.TYPE_INT_RGB);app.printAll(im.createGraphics());ImageIO.write(im,"png",new File(args[1]));System.exit(0);}
        SwingUtilities.invokeLater(()->{JFrame frame=new JFrame("P3 CPU 自动评测机");JudgeApp app=new JudgeApp(base);frame.setContentPane(app);frame.setMinimumSize(new Dimension(1000,760));frame.setSize(1220,940);frame.setLocationRelativeTo(null);frame.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE);frame.addWindowListener(new WindowAdapter(){public void windowClosing(WindowEvent e){if(app.running!=null)app.running.destroyForcibly();frame.dispose();System.exit(0);}});frame.setVisible(true);});
    }
}
