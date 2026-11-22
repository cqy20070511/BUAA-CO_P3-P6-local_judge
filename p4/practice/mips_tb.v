`timescale 1ns / 1ps
module mips_tb;
    reg clk;
    reg reset;
    mips uut(.clk(clk), .reset(reset));
    initial begin
        clk = 1'b0;
        reset = 1'b1;
        repeat (2) @(posedge clk);
        @(negedge clk);
        reset = 1'b0;
        repeat (400) @(posedge clk);
        #1;
        $display("P4 practice simulation finished.");
        $finish;
    end
    always #5 clk = ~clk;
endmodule
