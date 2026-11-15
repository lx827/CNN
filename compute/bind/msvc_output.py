"""按 MSVC 的控制台输出代码页（无控制台时用 ANSI）解码，向 CMake 输出 UTF-8。"""

import ctypes
import subprocess
import sys


def main() -> int:
    kernel = ctypes.windll.kernel32
    # 无控制台时 MSVC 使用系统 ANSI 代码页。
    codepage = kernel.GetConsoleOutputCP() or kernel.GetACP()
    result = subprocess.run(
        sys.argv[1:], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    sys.stdout.buffer.write(result.stdout.decode(f"cp{codepage}").encode("utf-8"))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
