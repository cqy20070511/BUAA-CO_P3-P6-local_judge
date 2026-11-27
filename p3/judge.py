"""P3 Logisim 加指令练习评测：调用随包 PracticeRunner（Java + Logisim 2.7.1）。"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
JAR = ROOT / "practice.jar"
LIB = ROOT / "lib"
STATUS = {"PASS": "AC", "WA": "WA", "TEST_ERROR": "WA", "ERROR": "RE"}
MESSAGE = {"AC": "Accepted.", "WA": "CPU 行为与期望不一致", "RE": "评测工具或电路适配错误"}
LINE = re.compile(r"^\[(\d+)/(\d+)\]\s+(\S+)\s+(PASS|WA|TEST_ERROR|ERROR)\s+(\S+)\s+\((\d+) cycles,\s*(\d+) ms\)\s*$")


def manifest():
    return json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))


def find_java():
    candidates = []
    if os.environ.get("JAVA_HOME"):
        for name in ("java.exe", "java"):
            candidates.append(Path(os.environ["JAVA_HOME"]) / "bin" / name)
    found = shutil.which("java")
    if found:
        candidates.append(Path(found))
    for location in (r"C:\Program Files\Eclipse Adoptium", r"C:\Program Files\Java", r"C:\Program Files\Microsoft"):
        base = Path(location)
        if base.is_dir():
            for folder in sorted(base.iterdir(), reverse=True):
                candidates.append(folder / "bin" / "java.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("未找到 Java 8 或更高版本；P3 的 Logisim 评测需要 Java。")


def judge(problem, source, on_result=None, timeout=1800):
    spec = manifest().get(problem.upper())
    if not spec:
        raise ValueError("题号不存在")
    source = Path(source).resolve()
    if source.is_dir():
        circuits = list(source.glob("*.circ"))
        if len(circuits) != 1:
            raise ValueError("P3 需要且只需要一个 .circ 文件")
        source = circuits[0]
    if source.suffix.lower() != ".circ" or not source.is_file():
        raise ValueError("P3 需要 .circ 文件")
    java = find_java()
    out = ROOT / "results" / (time.strftime("%Y%m%d_%H%M%S") + "_" + spec["id"] + "_" + str(time.time_ns() % 1000000))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise RuntimeError("结果目录已存在")
    classpath = f"{JAR}{os.pathsep}{LIB / '*'}"
    command = [java, "-Dfile.encoding=UTF-8", "-Djava.awt.headless=true", "-Xmx768m", "-cp", classpath, "PracticeRunner",
               "--root", str(ROOT), "--cpu", str(source), "--exercise", spec["id"], "--out", str(out)]
    started = time.time()
    results = []
    by_case = {item["id"]: item for item in spec["cases"]}
    logs = []
    try:
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as error:
        raise RuntimeError(f"无法启动 Java：{error}")

    def emit(item):
        results.append(item)
        if on_result:
            on_result(item)

    def handle(line):
        logs.append(line.rstrip())
        match = LINE.match(line.strip())
        if not match:
            return
        _, _, exercise, status, case, cycles, ms = match.groups()
        status = STATUS.get(status, "RE")
        title = by_case.get(case, {}).get("title", case)
        label = by_case.get(case, {}).get("label", "")
        emit(dict(id=case, title=title, label=label, status=status, cycles=int(cycles),
                  message=MESSAGE.get(status, status), detail="", ms=int(ms)))

    timer = threading.Timer(timeout, process.kill)
    timer.start()
    try:
        for line in process.stdout:
            handle(line)
        process.wait()
    finally:
        timer.cancel()
    seconds = round(time.time() - started, 3)
    if process.returncode == -9 and not results:
        raise RuntimeError("P3 评测超时")

    csv_path = out / "results.csv"
    if csv_path.is_file():
        import csv
        with csv_path.open(encoding="utf-8-sig", newline="") as handle_csv:
            rows = list(csv.DictReader(handle_csv))
        existing = {item["id"]: item for item in results}
        for row in rows:
            case = row.get("case", "")
            status = STATUS.get(row.get("status", ""), "RE")
            reason = (row.get("reason") or "").strip()
            item = existing.get(case)
            if item is None:
                title = by_case.get(case, {}).get("title", case)
                label = by_case.get(case, {}).get("label", "")
                item = dict(id=case, title=title, label=label, status=status,
                            cycles=int(row.get("cycles") or 0), message=MESSAGE.get(status, status),
                            detail=reason, ms=0)
                results.append(item)
                existing[case] = item
            else:
                item["status"] = status
                item["message"] = MESSAGE.get(status, status)
                item["detail"] = reason
    if not results:
        tail = "\n".join(logs[-20:])
        raise RuntimeError("P3 评测未产生结果" + (("：" + tail) if tail else ""))
    for item in results:
        item["budget"] = by_case.get(item["id"], {}).get("cycles", item.get("cycles", 0))
    passed = sum(item["status"] == "AC" for item in results)
    return dict(problem=spec["id"], encoding="practice", backend="logisim", results=results,
                passed=passed, total=len(results), seconds=seconds, record=str(out))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="P3 Logisim 加指令练习评测")
    parser.add_argument("problem")
    parser.add_argument("source")
    args = parser.parse_args()
    result = judge(args.problem, args.source, on_result=lambda item: print(item["label"], item["id"], item["status"]))
    print(f"通过 {result['passed']} / {result['total']}，记录：{result['record']}")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
