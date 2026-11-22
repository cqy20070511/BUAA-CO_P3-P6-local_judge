"""P4 逐点仿真评测：加指令练习与 2025 真题（wasm / native）。"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent
LINE = re.compile(r"^(?:\d+\s*)?@([0-9a-fxz]+):\s*([*$])\s*([0-9a-fxz]+)\s*<=\s*([0-9a-fxz]+)$", re.I)
NAMES = {"AC": "ACCEPTED", "WA": "WRONG ANSWER", "TLE": "TIME LIMIT EXCEEDED", "CE": "COMPILE ERROR", "RE": "RUNTIME ERROR"}


def manifest():
    return json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))


def parse(raw):
    match = LINE.match(raw.strip())
    if not match:
        return None
    pc, kind, location, value = match.groups()
    if re.search("[xz]", pc + location + value, re.I):
        return ("UNKNOWN", "出现未知值：" + raw.strip())
    if kind == "$":
        register = int(location, 10)
        if register == 0:
            return None
        return (kind, f"@{int(pc, 16):08x}: ${register} <= {int(value, 16):08x}")
    return (kind, f"@{int(pc, 16):08x}: *{int(location, 16):08x} <= {int(value, 16):08x}")


def evaluate(expected_lines, output, returncode=0, timed_out=False):
    expected = [item for item in (parse(line) for line in expected_lines) if item]
    actual = []
    for line in output.splitlines():
        item = parse(line)
        if not item:
            continue
        if item[0] == "UNKNOWN":
            return dict(status="WA", message=item[1])
        actual.append(item)

    if not actual and expected:
        return dict(status="WA", message="没有检测到写入日志；请让 CPU 按课程格式输出，或保留 regwrite/RegAddr/RegData/Memwrite/addr/WD/pc 等标准信号")

    for index, (want, got) in enumerate(zip(expected, actual)):
        if want != got:
            return dict(status="WA", message="写入行为不一致", index=index + 1, expected=want[1], actual=got[1])
    if len(actual) > len(expected):
        return dict(status="WA", message="出现多余写入", index=len(expected) + 1, expected="无后续写入", actual=actual[len(expected)][1])
    if timed_out:
        return dict(status="TLE", message="仿真进程超过墙钟时间上限")
    if returncode:
        return dict(status="RE", message="仿真异常退出", detail=output[-3000:])
    if len(actual) < len(expected):
        limit = "JUDGE_END" not in output
        return dict(status="TLE" if limit else "WA", message="周期上限内未完成" if limit else "仿真提前结束，缺少写入",
                    index=len(actual) + 1, expected=expected[len(actual)][1], actual="未发生")
    if "JUDGE_END" not in output:
        return dict(status="TLE", message="未观察到结束标记")
    match = re.search(r"JUDGE_END cycles=(\d+)", output)
    return dict(status="AC", message="Accepted.", cycles=int(match.group(1)) if match else None)


def runtime():
    override = os.environ.get("P6_IVERILOG")
    bundled = ROOT / "runtime" / "iverilog"
    if override:
        base = Path(override)
    elif (bundled / "bin" / "iverilog.exe").exists():
        base = bundled
    else:
        exe = shutil.which("iverilog")
        if not exe:
            raise RuntimeError("找不到原生 Icarus。请设置 P6_IVERILOG，或使用默认 wasm 后端。")
        return exe, shutil.which("vvp"), None
    return str(base / "bin" / "iverilog.exe"), str(base / "bin" / "vvp.exe"), base / "lib" / "ivl"


def extract_zip(source, dest):
    total = 0
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            relative = Path(item.filename.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in item.filename:
                raise ValueError("ZIP 路径不安全")
            if item.is_dir() or relative.suffix.lower() not in (".v", ".vh"):
                continue
            total += item.file_size
            if total > 20 * 1024 * 1024:
                raise ValueError("源码解压后超过 20MB")
            path = dest / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(item))


def prepare_sources(source, dest):
    source = Path(source).resolve()
    if source.is_file() and source.suffix.lower() == ".zip":
        extract_zip(source, dest)
    elif source.is_file() and source.suffix.lower() == ".v":
        shutil.copy2(source, dest / source.name)
    elif source.is_dir():
        paths = [p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".v", ".vh")]
        if len(paths) > 500:
            raise ValueError("源码文件过多，请只提交当前题的 RTL 工程")
        for path in paths:
            if any(part.startswith(".") for part in path.relative_to(source).parts):
                continue
            target = dest / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    else:
        raise ValueError("请选择源码目录、Verilog 文件或 ZIP")
    units = []
    for path in dest.rglob("*.v"):
        if re.search(r"(^tb[_.]|_tb(?:_|\.)|^testbench|^mips_txt)", path.name, re.I):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
        bad = re.search(r"\$(finish|stop|fatal|fopen|system)\b", stripped)
        if bad:
            raise ValueError(f"{path.name} 含不允许的仿真任务 ${bad.group(1)}；P4 的日志和 IM 读取可以保留")
        units.append(path)
    if not units:
        raise ValueError("没有找到 RTL .v 文件")
    if sum(bool(re.search(r"\bmodule\s+mips\b", p.read_text(errors="replace"))) for p in units) != 1:
        raise ValueError("必须且只能有一个顶层 module mips；不要把多个题的工程一起提交")
    return units


def run_process(args, cwd, timeout):
    env = os.environ.copy()
    env["PATH"] = str(Path(args[0]).parent) + os.pathsep + env.get("PATH", "")
    env["TEMP"] = env["TMP"] = "."
    return subprocess.run([str(x) for x in args], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def prints_write_log(sources):
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'\$display\s*\(\s*"[^"]*@[^"]*<=', text):
            return True
    return False


def top_can_be_probed(sources):
    top = ""
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"\bmodule\s+mips\b(.*?)\bendmodule\b", text, re.S)
        if match:
            top = match.group(1)
            break
    if not top:
        return False
    names = ("regwrite", "RegAddr", "RegData", "Memwrite", "addr", "WD", "pc")
    return all(re.search(r"\b" + name + r"\b", top) for name in names)


PROBE_TB = """`timescale 1ns/1ps
module p4_probe_tb;
    reg clk = 1'b0;
    reg reset = 1'b1;
    integer budget;
    mips dut(.clk(clk), .reset(reset));
    always #5 clk = ~clk;
    always @(posedge clk) begin
        if (!reset) begin
            if (dut.regwrite && dut.RegAddr != 0) $display("@%h: $%0d <= %h", dut.pc, dut.RegAddr, dut.RegData);
            if (dut.Memwrite) $display("@%h: *%h <= %h", dut.pc, dut.addr, dut.WD);
        end
    end
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
"""


def judge(problem, source, encoding="practice", case_ids=None, on_result=None, timeout=15, save=True, defines=(), backend=None):
    spec = manifest().get(problem.upper())
    if not spec:
        raise ValueError("题号不存在")
    problem = spec["id"]
    backend = backend or os.environ.get("P4_JUDGE_BACKEND", "wasm")
    if backend not in ("native", "wasm"):
        raise ValueError("仿真后端须为 wasm 或 native")
    if encoding != "practice":
        raise ValueError("P4 只有练习编码")
    cases = [case for case in spec["cases"] if not case_ids or case["id"] in case_ids]
    if not cases:
        raise ValueError("没有选中的测试点")

    root = ROOT / "runs"
    root.mkdir(exist_ok=True)
    record = root / (time.strftime("%Y%m%d_%H%M%S") + "_" + problem + "_" + str(time.time_ns() % 1000000))
    if save:
        record.mkdir()
    reports = []
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="job_", dir=str(root)) as temp:
        work = Path(temp)
        sources = work / "src"
        sources.mkdir()
        compile_status = "CE"
        try:
            units = prepare_sources(source, sources)
            tb_path = ROOT / "p4_judge_tb.v"
            top_name = "p4_judge_tb"
            if not prints_write_log(units) and top_can_be_probed(units):
                tb_path = work / "p4_probe_tb.v"
                tb_path.write_text(PROBE_TB, encoding="utf-8")
                top_name = "p4_probe_tb"
            tb_name = tb_path.name
            if backend == "wasm":
                node = shutil.which("node")
                if not node:
                    raise RuntimeError("未找到 Node.js；请安装 Node.js 20 或更新版本，或设置 P4_JUDGE_BACKEND=native。")
                config = dict(work=str(work), files=[str(p) for p in sources.rglob("*") if p.is_file()],
                              units=list(map(str, units)), include=list(map(str, sorted({u.parent for u in units}))),
                              defines=list(defines), output=str(work / "submission.vvp"),
                              tb=str(tb_path), top=top_name)
                config_file = work / "compile.json"
                config_file.write_text(json.dumps(config), encoding="utf-8")
                args = [node, str(ROOT.parent / "tools" / "wasm_runner.mjs"), "compile", str(config_file)]
            else:
                iv, vvp, lib = runtime()
                args = [iv]
                if lib:
                    args += ["-B", os.path.relpath(str(lib), str(work))]
                args += ["-g2005", "-s", top_name, "-o", "submission.vvp"]
                for value in defines:
                    args += ["-D" + value]
                for directory in sorted({u.parent for u in units}):
                    args += ["-I", os.path.relpath(str(directory), str(work))]
                shutil.copy2(tb_path, work / tb_name)
                args += [os.path.relpath(str(u), str(work)) for u in units] + [tb_name]
            compiled = run_process(args, work, 30)
            diagnostics = compiled.stdout + compiled.stderr
            ce = compiled.returncode != 0
            if ce and not diagnostics.strip():
                diagnostics = "Icarus 编译进程异常退出，退出码：" + str(compiled.returncode)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            diagnostics = str(error)
            ce = True
            if isinstance(error, (OSError, RuntimeError)):
                compile_status = "RE"
        if save:
            (record / "compile.log").write_text(diagnostics, encoding="utf-8")

        for case in cases:
            case_root = ROOT / spec["path"] / case["id"]
            expected = (case_root / "expected.log").read_text(encoding="utf-8-sig").splitlines()
            if ce:
                result = dict(status=compile_status, message="编译器进程异常，需先检查仿真环境" if compile_status == "RE" else "Verilog 编译或接口检查失败", detail=diagnostics[-6000:])
            else:
                shutil.copy2(case_root / "code.txt", work / "code.txt")
                if backend == "wasm":
                    args = [node, str(ROOT.parent / "tools" / "wasm_runner.mjs"), "run",
                            str(work / "submission.vvp"), str(work / "code.txt"), "+budget=" + str(case["cycles"])]
                else:
                    args = [vvp]
                    if lib:
                        args += ["-M", "-", "-M", os.path.relpath(str(lib), str(work))]
                    args += ["submission.vvp", "+budget=" + str(case["cycles"])]
                try:
                    run = run_process(args, work, timeout)
                    output = run.stdout + run.stderr
                    result = evaluate(expected, output, run.returncode)
                except subprocess.TimeoutExpired as error:
                    output = error.stdout or ""
                    if isinstance(output, bytes):
                        output = output.decode("utf-8", errors="replace")
                    result = evaluate(expected, output, timed_out=True)
                except OSError as error:
                    output = str(error)
                    result = dict(status="RE", message=str(error))
                if save:
                    (record / (case["id"] + ".log")).write_text(output, encoding="utf-8")
            result = {**result, "id": case["id"], "title": case["title"], "budget": case["cycles"]}
            reports.append(result)
            if on_result:
                on_result(result)

    summary = dict(problem=problem, encoding=encoding, backend=backend, results=reports,
                   passed=sum(r["status"] == "AC" for r in reports), total=len(reports),
                   seconds=round(time.time() - started, 3), record=str(record) if save else None)
    if save:
        (record / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="P4 逐点仿真评测")
    parser.add_argument("problem")
    parser.add_argument("source")
    parser.add_argument("--case", nargs="+", dest="cases")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--backend", choices=["wasm", "native"], default=None)
    args = parser.parse_args()
    result = judge(args.problem, args.source, case_ids=args.cases, backend=args.backend)
    print(f"通过 {result['passed']} / {result['total']}，记录：{result['record']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
