`timescale 1ns/1ps
module p7_capture;
reg clk=0,reset=1,interrupt=0;
wire [31:0] macroscopic_pc,i_inst_addr,m_data_addr,m_data_wdata,m_inst_addr,w_inst_addr,w_grf_wdata,m_int_addr;
wire [3:0] m_data_byteen,m_int_byteen;
wire [4:0] w_grf_addr;wire w_grf_we;
reg [31:0] inst[0:4095];reg [31:0] data[0:3071];
wire [31:0] i_inst_rdata=(i_inst_addr>=32'h3000 && i_inst_addr<32'h7000) ? inst[(i_inst_addr-32'h3000)>>2] : 32'hffffffff;
wire [31:0] m_data_rdata=(m_data_addr<32'h3000) ? data[m_data_addr>>2] : 32'b0;
mips dut(.clk(clk),.reset(reset),.interrupt(interrupt),.macroscopic_pc(macroscopic_pc),
 .i_inst_addr(i_inst_addr),.i_inst_rdata(i_inst_rdata),.m_data_addr(m_data_addr),.m_data_rdata(m_data_rdata),
 .m_data_wdata(m_data_wdata),.m_data_byteen(m_data_byteen),.m_int_addr(m_int_addr),.m_int_byteen(m_int_byteen),
 .m_inst_addr(m_inst_addr),.w_grf_we(w_grf_we),.w_grf_addr(w_grf_addr),.w_grf_wdata(w_grf_wdata),.w_inst_addr(w_inst_addr));
integer i,lane,cycles=0,budget=12000,drain=0,irq_count=0,dummy;
integer mid_reset=0,reset_hold=0,reset_irq=0;reg mid_fired=0;reg [31:0] reset_pc;
reg [31:0] finish_pc,targets[0:7],merged,temp_target;reg [7:0] fired=0;
reg done=0,ack_seen=0;
always #5 clk=~clk;
initial begin
 dummy=$value$plusargs("budget=%d",budget);dummy=$value$plusargs("finish_pc=%h",finish_pc);
 dummy=$value$plusargs("irq_count=%d",irq_count);
 dummy=$value$plusargs("mid_reset=%d",mid_reset);dummy=$value$plusargs("reset_pc=%h",reset_pc);
 dummy=$value$plusargs("reset_irq=%d",reset_irq);
 dummy=$value$plusargs("irq0=%h",temp_target);targets[0]=temp_target;
 dummy=$value$plusargs("irq1=%h",temp_target);targets[1]=temp_target;
 dummy=$value$plusargs("irq2=%h",temp_target);targets[2]=temp_target;
 dummy=$value$plusargs("irq3=%h",temp_target);targets[3]=temp_target;
 dummy=$value$plusargs("irq4=%h",temp_target);targets[4]=temp_target;
 dummy=$value$plusargs("irq5=%h",temp_target);targets[5]=temp_target;
 dummy=$value$plusargs("irq6=%h",temp_target);targets[6]=temp_target;
 dummy=$value$plusargs("irq7=%h",temp_target);targets[7]=temp_target;
 $readmemh("code.txt",inst);
 for(i=0;i<3072;i=i+1)data[i]=0;
 repeat(3)@(negedge clk);reset=0;
end
always @(posedge clk) begin
 if(reset && mid_fired)begin
  if(w_grf_we!==0 || m_data_byteen!==0 || m_int_byteen!==0)begin $display("P7_BAD write_during_reset");$finish;end
  for(i=0;i<3072;i=i+1)data[i]<=0;
 end else if(!reset)begin
  cycles=cycles+1;
  if((^m_data_byteen)===1'bx || w_grf_we===1'bx || (^m_int_byteen)===1'bx)begin
   $display("P7_BAD unknown_enable %0d",cycles);$finish;
  end
  if(|m_data_byteen)begin
   if((^m_data_addr)===1'bx || m_data_addr>=32'h3000)begin $display("P7_BAD dm_address %h",m_data_addr);$finish;end
   merged=data[m_data_addr>>2];
   for(lane=0;lane<4;lane=lane+1)if(m_data_byteen[lane])merged[lane*8+:8]=m_data_wdata[lane*8+:8];
   data[m_data_addr>>2]<=merged;
   $display("P7_DM %0d %h %h %h %h %h",cycles,m_inst_addr,m_data_addr,m_data_byteen,m_data_wdata,merged);
  end
  if(|m_int_byteen)begin
   if((m_int_addr&32'hfffffffc)!=32'h7f20)begin $display("P7_BAD int_address %h",m_int_addr);$finish;end
   $display("P7_INT %0d %h %h %h",cycles,m_inst_addr,m_int_addr,m_int_byteen);ack_seen=1;
  end
  if(w_grf_we && w_grf_addr!=0)begin
   $display("P7_GRF %0d %h %0d %h",cycles,w_inst_addr,w_grf_addr,w_grf_wdata);
   if(w_inst_addr===finish_pc && w_grf_addr===30 && w_grf_wdata===32'hcafe)begin done=1;drain=12;end
  end
 end
end
always @(negedge clk)begin
 if(reset && mid_fired && reset_hold>0)begin
  reset_hold=reset_hold-1;
  if(reset_hold==0)begin
   reset=0;interrupt=0;cycles=0;fired=0;done=0;ack_seen=0;
   $display("P7_RESET_END");
  end
 end else if(!reset)begin
  if(mid_reset && !mid_fired && (macroscopic_pc&32'hfffffffc)==reset_pc)begin
   reset=1;mid_fired=1;reset_hold=3;interrupt=reset_irq;done=0;drain=0;
   $display("P7_RESET_BEGIN %h",reset_pc);
  end
  if(ack_seen)begin interrupt=0;ack_seen=0;end
  for(i=0;i<irq_count;i=i+1)begin
   if(!fired[i] && (macroscopic_pc&32'hfffffffc)==targets[i])begin
    fired[i]=1;interrupt=1;$display("P7_ARM %0d %h",cycles,targets[i]);
   end
  end
  if(done)begin
   if(drain==0)begin $display("P7_DONE %0d",cycles);$finish;end
   drain=drain-1;
  end
  if(cycles>=budget)begin $display("P7_LIMIT %0d",cycles);$finish;end
 end
end
endmodule
