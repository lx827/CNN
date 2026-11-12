"""用固定开发依赖格式化手写原生源码；--check 只检查，不修改文件。"""

import argparse
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查格式，发现差异时非零退出")
    args = parser.parse_args()
    tracked = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
            "--",
            "lib",
            "bind",
            "tests/native",
            ":(exclude,glob)**/vendor/**",
            ":(exclude,glob)**/third_party/**",
            ":(exclude,glob)**/third-party/**",
            ":(exclude,glob)**/thirdparty/**",
        ],
        cwd=ROOT,
    )
    files = [
        name
        for name in tracked.decode("utf-8").split("\0")
        if name and Path(name).suffix in SUFFIXES
    ]
    flags = ["--dry-run", "--Werror", "--ferror-limit=1"] if args.check else ["-i"]
    result = subprocess.run(["clang-format", "--style=file", *flags, *files], cwd=ROOT)
    print(f"clang-format {'检查' if args.check else '格式化'} {len(files)} 个手写源码文件")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
