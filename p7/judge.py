"""P7 五级流水线 CPU 的逐点评测：外置端口采集 + expected.json 判定。"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
NAMES = {"AC": "ACCEPTED", "WA": "WRONG ANSWER", "TLE": "TIME LIMIT EXCEEDED", "CE": "COMPILE ERROR", "RE": "RUNTIME ERROR"}
LINE_GRF = re.compile(r"^P7_GRF\s+(\d+)\s+([0-9a-fA-F]+)\s+(\d+)\s+([0-9a-fA-F]+)\s*$")
LINE_DM = re.compile(r"^P7_DM\s+(\d+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s*$")
LINE_INT = re.compile(r"^P7_INT\s+(\d+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s*$")
LINE_ARM = re.compile(r"^P7_ARM\s+(\d+)\s+([0-9a-fA-F]+)\s*$")


def manifest():
    return json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))


def hexs(value):
    if isinstance(value, int):
        return f"{value:08x}"
    return f"{int(str(value), 16):08x}"


def prepare_sources(source, dest):
    source = Path(source).resolve()
    if source.is_file() and source.suffix.lower() == ".zip":
        import zipfile
        with zipfile.ZipFile(source) as archive:
            archive.extractall(dest)
    elif source.is_file() and source.suffix.lower() in (".v", ".vh"):
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
        bad = re.search(r"\$(display|write|monitor|strobe|finish|stop|fatal|readmemh|readmemb|fopen|system)\b", stripped)
        if bad:
            raise ValueError(f"{path.name} 含不允许的仿真任务 ${bad.group(1)}；P7 请只提交 CPU RTL")
        units.append(path)
    if not units:
        raise ValueError("没有找到 RTL .v 文件")
    if sum(bool(re.search(r"\bmodule\s+mips\b", p.read_text(errors="replace"))) for p in units) != 1:
        raise ValueError("必须且只能有一个顶层 module mips")
    return units


def run_process(args, cwd, timeout):
    env = os.environ.copy()
    env["PATH"] = str(Path(args[0]).parent) + os.pathsep + env.get("PATH", "")
    env["TEMP"] = env["TMP"] = "."
    return subprocess.run([str(x) for x in args], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def parse_events(output):
    grf, dm, ints, arms, resets = [], [], [], [], []
    done = limit = False
    bad = []
    for line in output.splitlines():
        match = LINE_GRF.match(line)
        if match:
            grf.append((int(match.group(1)), match.group(2).lower(), int(match.group(3)), match.group(4).lower()))
            continue
        match = LINE_DM.match(line)
        if match:
            dm.append((int(match.group(1)), match.group(2).lower(), match.group(3).lower(), int(match.group(4), 16),
                       int(match.group(5), 16), int(match.group(6), 16)))
            continue
        match = LINE_INT.match(line)
        if match:
            ints.append((int(match.group(1)), match.group(2).lower(), match.group(3).lower(), int(match.group(4), 16)))
            continue
        match = LINE_ARM.match(line)
        if match:
            arms.append((int(match.group(1)), match.group(2).lower()))
            continue
        if line.startswith("P7_DONE"):
            done = True
        elif line.startswith("P7_LIMIT"):
            limit = True
        elif line.startswith("P7_BAD"):
            bad.append(line.strip())
        elif line.startswith("P7_RESET_BEGIN"):
            resets.append(("begin", line.split()[-1].lower()))
        elif line.startswith("P7_RESET_END"):
            resets.append(("end", ""))
    return grf, dm, ints, arms, resets, done, limit, bad


def compare_exact(case, expected, parsed):
    grf, dm, ints, arms, resets, done, limit, bad = parsed
    if bad:
        return dict(status="WA", message="复位/使能检查失败", detail=bad[0])
    if limit:
        return dict(status="TLE", message="超过周期上限")
    if not done:
        return dict(status="WA", message="未到达完成标记", detail="没有看到 P7_DONE")
    return compare_exact_events(case, expected, grf, dm, ints, arms)


def compare_exact_events(case, expected, grf, dm, ints, arms):
    eg, ed, ei = expected.get("grf", []), expected.get("dm", []), expected.get("int", [])
    if len(grf) != len(eg):
        return dict(status="WA", message=f"GRF 写入数不一致：期望 {len(eg)}，实际 {len(grf)}")
    for index, (actual, exp) in enumerate(zip(grf, eg)):
        allowed = [str(x).lower() for x in exp.get("allowed_values", [exp["value"]])]
        if actual[1] != hexs(exp["pc"]) or actual[2] != int(exp["reg"]) or actual[3] not in allowed:
            return dict(status="WA", message=f"第 {index + 1} 个 GRF 写入不一致",
                        expected=f'{exp["pc"]} ${exp["reg"]} <= {"|".join(allowed)}',
                        actual=f'{actual[1]} ${actual[2]} <= {actual[3]}')
    if len(dm) != len(ed):
        return dict(status="WA", message=f"DM 写入数不一致：期望 {len(ed)}，实际 {len(dm)}")
    for index, (actual, exp) in enumerate(zip(dm, ed)):
        mask = int(exp["value_mask"], 16)
        write_bits = int(exp["write_bits"], 16)
        if (actual[1] != hexs(exp["pc"]) or actual[2] != hexs(exp["address"]) or actual[3] != int(exp["byteen"])
                or (actual[4] & mask) != (write_bits & mask) or actual[5] != int(exp["merged_word"], 16)):
            return dict(status="WA", message=f"第 {index + 1} 个 DM 写入不一致",
                        expected=f'{exp["pc"]} *{exp["address"]} byteen={exp["byteen"]} merged={exp["merged_word"]}',
                        actual=f'{actual[1]} *{actual[2]} byteen={actual[3]} merged={actual[5]:08x}')
    if len(ints) != len(ei):
        return dict(status="WA", message=f"中断响应数不一致：期望 {len(ei)}，实际 {len(ints)}")
    for index, (actual, exp) in enumerate(zip(ints, ei)):
        if actual[1] != hexs(exp["pc"]) or actual[2] != hexs(exp["address"]) or actual[3] != int(exp["byteen"]):
            return dict(status="WA", message=f"第 {index + 1} 个中断响应不一致",
                        expected=f'{exp["pc"]} *{exp["address"]} byteen={exp["byteen"]}',
                        actual=f'{actual[1]} *{actual[2]} byteen={actual[3]}')
    targets = [str(item["target_pc"]).lower() for item in case.get("interrupts", [])]
    if [target for _, target in arms] != targets:
        return dict(status="WA", message="中断注入目标没有按规则触发",
                    expected=", ".join(targets) or "无", actual=", ".join(t for _, t in arms) or "无")
    return dict(status="AC", message="Accepted.", detail=f"GRF {len(grf)} 条、DM {len(dm)} 条、INT {len(ints)} 条")


def evaluate_timer(case, expected, parsed):
    grf, dm, ints, arms, resets, done, limit, bad = parsed
    if bad:
        return dict(status="WA", message="复位/使能检查失败", detail=bad[0])
    if limit:
        return dict(status="TLE", message="超过周期上限")
    if not done:
        return dict(status="WA", message="未到达完成标记")
    if len(ints) != expected.get("external_ack_count", 0):
        return dict(status="WA", message="外部中断确认写入数不一致")
    regs = [0] * 32
    memory = [0] * 3072
    for _, pc, reg, value in grf:
        if reg:
            regs[reg] = int(value, 16)
    for _, pc, addr, byteen, wdata, merged in dm:
        address = int(addr, 16)
        if address < 0x3000:
            memory[address >> 2] = merged
    handler = hexs(case.get("labels", {}).get("handler", "00004180"))
    entries = [item for item in grf if item[1] == handler]
    if len(entries) != expected.get("handler_entries", len(entries)):
        return dict(status="WA", message=f"handler 进入次数不一致：期望 {expected.get('handler_entries')}，实际 {len(entries)}")
    for left, right in zip(entries, entries[1:]):
        if right[0] - left[0] < expected.get("min_handler_gap_cycles", 0):
            return dict(status="WA", message="连续 handler 入口间隔不足",
                        expected=f">= {expected.get('min_handler_gap_cycles')}", actual=f"{right[0] - left[0]}")
    cause = next((int(item[3], 16) for item in grf if item[1] == handler and item[2] == expected.get("cause_register")), None)
    epc_pc = hexs(int(handler, 16) + 4)
    epc = next((int(item[3], 16) for item in grf if item[1] == epc_pc and item[2] == expected.get("epc_register")), None)
    if cause is None or ((cause >> 2) & 0x1f) != expected.get("cause_exccode", 0):
        return dict(status="WA", message="Cause.ExcCode 不符合 Timer 契约", expected=str(expected.get("cause_exccode")), actual="—" if cause is None else str((cause >> 2) & 0x1f))
    if epc is None or epc < int(expected["allowed_epc_min"], 16) or epc > int(expected["allowed_epc_max"], 16) or epc & 3:
        return dict(status="WA", message="EPC 不在允许的程序区间", expected=f'{expected["allowed_epc_min"]}..{expected["allowed_epc_max"]}', actual="—" if epc is None else hexs(epc))
    for check in expected.get("read_checks", []):
        target_pc, reg = hexs(check["pc"]), int(check["reg"])
        values = [int(item[3], 16) for item in grf if item[1] == target_pc and item[2] == reg]
        if not values:
            return dict(status="WA", message=f"没有观察到 {check['purpose']}")
        value = values[-1]
        if value < check["minimum"] or value > check["maximum"]:
            return dict(status="WA", message=f'{check["purpose"]} 超出范围',
                        expected=f'{check["minimum"]}..{check["maximum"]}', actual=str(value))
    poison = expected.get("eret_poison_pc", "").lower()
    if poison and any(item[1] == poison for item in grf + dm + ints):
        return dict(status="WA", message="执行到了 eret 的错路标记")
    for reg, value in expected.get("final_registers", {}).items():
        if regs[int(reg)] != int(value, 16):
            return dict(status="WA", message=f"最终 ${reg} 不一致", expected=value, actual=hexs(regs[int(reg)]))
    for address, value in expected.get("final_memory", {}).items():
        word = memory[int(address, 16) >> 2]
        if word != int(value, 16):
            return dict(status="WA", message=f"最终 DM[{address}] 不一致", expected=value, actual=hexs(word))
    return dict(status="AC", message="Accepted.", detail=f"handler {len(entries)} 次，Timer 契约通过")


def evaluate(case, expected, output, returncode=0):
    if "P7_BAD" in output:
        return dict(status="WA", message="复位/使能检查失败", detail=next((line for line in output.splitlines() if line.startswith("P7_BAD")), ""))
    mid_reset = bool(case.get("mid_reset"))
    if mid_reset:
        lines = output.splitlines()
        ends = [i for i, line in enumerate(lines) if line.startswith("P7_RESET_END")]
        begins = [line for line in lines if line.startswith("P7_RESET_BEGIN")]
        if not ends or not begins:
            return dict(status="WA", message="运行中复位没有发生")
        output = "\n".join(lines[ends[-1] + 1:])
    parsed = parse_events(output)
    if expected.get("mode") == "timer_contract":
        return evaluate_timer(case, expected, parsed)
    return compare_exact(case, expected, parsed)


def judge(problem, source, on_result=None, timeout=25, save=True, case_ids=None):
    spec = manifest().get(problem.upper())
    if not spec:
        raise ValueError("题号不存在")
    cases = [case for case in spec["cases"] if not case_ids or case["id"] in case_ids]
    root = ROOT / "runs"
    root.mkdir(exist_ok=True)
    record = root / (time.strftime("%Y%m%d_%H%M%S") + "_" + spec["id"] + "_" + str(time.time_ns() % 1000000))
    if save:
        record.mkdir()
    reports = []
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="job_", dir=str(root)) as temp:
        work = Path(temp)
        sources = work / "src"
        sources.mkdir()
        try:
            units = prepare_sources(source, sources)
            node = shutil.which("node")
            if not node:
                raise RuntimeError("未找到 Node.js；P7 需要 Node.js 20 或更新版本")
            config = dict(work=str(work), files=[str(p) for p in sources.rglob("*") if p.is_file()],
                          units=list(map(str, units)), include=list(map(str, sorted({u.parent for u in units}))),
                          defines=[], output=str(work / "submission.vvp"),
                          tb=str(ROOT / "protocol" / "port_capture_tb.v"), top="p7_capture")
            config_file = work / "compile.json"
            config_file.write_text(json.dumps(config), encoding="utf-8")
            args = [node, ROOT.parent / "tools" / "wasm_runner.mjs", "compile", config_file]
            compiled = run_process(args, work, 60)
            diagnostics = compiled.stdout + compiled.stderr
            ce = compiled.returncode != 0
            if ce and not diagnostics.strip():
                diagnostics = "Icarus 编译进程异常退出，退出码：" + str(compiled.returncode)
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            diagnostics = str(error)
            ce = True
        if save:
            (record / "compile.log").write_text(diagnostics, encoding="utf-8")
        for case in cases:
            case_root = ROOT / spec["path"] / case["id"]
            expected = json.loads((case_root / "expected.json").read_text(encoding="utf-8"))
            if ce:
                result = dict(status="CE", message="Verilog 编译或接口检查失败", detail=diagnostics[-6000:])
            else:
                shutil.copy2(case_root / "code.txt", work / "code.txt")
                args = [node, ROOT.parent / "tools" / "wasm_runner.mjs", "run", work / "submission.vvp", work / "code.txt"]
                args += ["+budget=" + str(case["cycles"]), "+finish_pc=" + str(case["finish_pc"])]
                irqs = case.get("interrupts") or []
                if irqs:
                    args.append("+irq_count=" + str(len(irqs)))
                    for index, item in enumerate(irqs[:8]):
                        args.append(f"+irq{index}=" + str(item["target_pc"]))
                mid = case.get("mid_reset")
                if mid:
                    args += ["+mid_reset=1", "+reset_pc=" + str(mid["target_pc"]),
                             "+reset_irq=" + str(mid.get("interrupt_during_reset", 0))]
                try:
                    run = run_process(args, work, timeout)
                    output = run.stdout + run.stderr
                    result = evaluate(case, expected, output, run.returncode)
                except subprocess.TimeoutExpired as error:
                    output = error.stdout or ""
                    if isinstance(output, bytes):
                        output = output.decode("utf-8", errors="replace")
                    result = dict(status="TLE", message="评测超时")
                except OSError as error:
                    output = str(error)
                    result = dict(status="RE", message=str(error))
                if save:
                    (record / (case["id"] + ".log")).write_text(output, encoding="utf-8")
            result = {**result, "id": case["id"], "title": case["title"], "budget": case["cycles"]}
            reports.append(result)
            if on_result:
                on_result(result)
    summary = dict(problem=spec["id"], encoding="practice", backend="wasm", results=reports,
                   passed=sum(item["status"] == "AC" for item in reports), total=len(reports),
                   seconds=round(time.time() - started, 3), record=str(record) if save else None)
    if save:
        (record / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="P7 逐点仿真评测")
    parser.add_argument("problem")
    parser.add_argument("source")
    args = parser.parse_args()
    result = judge(args.problem, args.source, on_result=lambda item: print(item["id"], item["status"], item["message"]))
    print(f"通过 {result['passed']} / {result['total']}")
