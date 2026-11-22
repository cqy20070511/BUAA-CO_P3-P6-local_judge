#!/usr/bin/env python3
"""生成不放进 Git 的 P5 / P6 派生测试数据。

P3 / P4 的测试点随仓库提供；P5（960 点）和 P6（936 点）的 code.txt /
expected.log 体积较大，由本脚本从固定输入生成。生成后即可启动网页。
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def count_cases(stage):
    base = ROOT if stage == "P6" else ROOT / "p5"
    data = json.loads((base / "cases.json").read_text(encoding="utf-8"))
    return sum(len(spec["cases"]) for spec in data.values())


def ensure(stage, force=False):
    base = ROOT if stage == "P6" else ROOT / "p5"
    tests = base / "tests"
    expected = count_cases(stage)
    if tests.is_dir() and not force:
        print(f"{stage}: 已有 {tests.relative_to(ROOT)}（{expected} 点），跳过。")
        return
    if force and tests.is_dir():
        shutil.rmtree(tests)
    print(f"{stage}: 生成 {expected} 个测试点……", flush=True)
    subprocess.run([sys.executable, "make_cases.py"], cwd=base, check=True)
    if not tests.is_dir():
        raise SystemExit(f"{stage}: 生成后没有找到 {tests}")


def verify(stage, expected):
    base = ROOT if stage == "P6" else ROOT / "p5"
    tests = base / "tests"
    count = sum(1 for _ in tests.rglob("code.txt")) if tests.is_dir() else 0
    print(f"{stage}: {count} 个测试点目录（预期 {expected}）")
    if count != expected:
        raise SystemExit(f"{stage}: 测试点数量不符")


def main():
    parser = argparse.ArgumentParser(description="生成 P5 / P6 测试数据")
    parser.add_argument("--force", action="store_true", help="删除并重新生成 P5 / P6 测试点")
    args = parser.parse_args()
    ensure("P6", args.force)
    ensure("P5", args.force)
    verify("P6", 936)
    verify("P5", 960)
    print("\n完成。现在可以运行 启动评测机.cmd 或 python server.py。")
    print("P3 的 283 点、P4 的 60 点测试随仓库提供，无需生成。")


if __name__ == "__main__":
    main()
