"""独立进程运行六个离线实验；任一失败立即返回非零退出码。"""
from pathlib import Path
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    switches = parser.add_mutually_exclusive_group()
    switches.add_argument("--trace", action="store_true", help="所有实验开启 LangSmith 追踪")
    switches.add_argument("--no-trace", action="store_true", help="所有实验关闭追踪")
    args = parser.parse_args()
    flags = ["--trace"] if args.trace else ["--no-trace"] if args.no_trace else []
    directory = Path(__file__).resolve().parent
    for pattern in ("01_*.py", "02_*.py", "03_*.py", "04_*.py", "05_*.py", "06_*.py"):
        paths = list(directory.glob(pattern))
        if len(paths) != 1:
            raise RuntimeError(f"实验脚本数量异常：{pattern}")
        print(f"\n=== {paths[0].name} ===", flush=True)
        subprocess.run([sys.executable, "-X", "utf8", str(paths[0]), *flags], check=True)
    print("\n全部六个离线实验通过。")


if __name__ == "__main__":
    main()
