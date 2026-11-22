`timescale 1ns/1ps
// P4 单周期评测：CPU 自己打印课程格式的写入日志，TB 只负责复位、计时和结束标记。
module p4_judge_tb;
    reg clk = 1'b0;
    reg reset = 1'b1;
    integer budget;
    mips dut(.clk(clk), .reset(reset));
    always #5 clk = ~clk;
    initial begin
        if (!$value$plusargs("budget=%d", budget)) budget = 400;
        repeat (2) @(posedge clk);
        @(negedge clk);
        reset = 1'b0;
        repeat (budget) @(posedge clk);
        #1;
        $display("JUDGE_END cycles=%0d", budget);
        $finish;
    end
endmodule
