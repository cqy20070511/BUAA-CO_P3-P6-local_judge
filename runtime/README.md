# 仿真运行库

wasm 目录中的 ivlpp、ivl、vvp 及其 JS 入口复制自工作区原有 `tmp/p5_5cpu_audit_20261110/wasm`，与 P5 练习评测器使用的运行库相同。

这三部分分别执行 Verilog 预处理、编译、仿真。运行它们需要本机 Node.js；Python 服务负责按题选择代码、设置周期上限、比较日志和展示结果，不通过网络调用远程评测。

Icarus Verilog 官方源码及许可证：[steveicarus/iverilog](https://github.com/steveicarus/iverilog)。预处理参数参考官方 [ivlpp/main.c](https://github.com/steveicarus/iverilog/blob/master/ivlpp/main.c)。本包自编的调用入口为 `tools/wasm_runner.mjs`。
