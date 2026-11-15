"""用 cargo 构建现有 edge cdylib，并生成包含薄 Python adapter 的二进制 wheel。"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import platform
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent
EDGE = ROOT.parents[1] / "edge"
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
PACKAGE = "dc24_driver_rust"
NAME = PROJECT["name"]
VERSION = PROJECT["version"]
DISTRIBUTION = NAME.replace("-", "_")
DIST_INFO = f"{DISTRIBUTION}-{VERSION}.dist-info"


def _platform_tag() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win_amd64"
    if sys.platform.startswith("linux"):
        architectures = {
            "x86_64": "x86_64",
            "amd64": "x86_64",
            "aarch64": "aarch64",
            "arm64": "aarch64",
        }
        if machine in architectures:
            return f"linux_{architectures[machine]}"
    raise RuntimeError(f"{NAME} 不支持当前平台: {sys.platform} {machine}")


def _metadata() -> bytes:
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {NAME}",
        f"Version: {VERSION}",
        f"Summary: {PROJECT['description']}",
        f"Requires-Python: {PROJECT['requires-python']}",
        *(f"Requires-Dist: {dependency}" for dependency in PROJECT["dependencies"]),
        "",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _wheel(tag: str) -> bytes:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: dc24_rust_build\n"
        "Root-Is-Purelib: false\n"
        f"Tag: {tag}\n"
        "\n"
    ).encode("utf-8")


def _native_library() -> Path:
    subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--locked",
            "--manifest-path",
            str(EDGE / "Cargo.toml"),
            "--target-dir",
            str(EDGE / "target"),
        ],
        cwd=EDGE,
        check=True,
    )
    name = "dc24_edge_core.dll" if sys.platform == "win32" else "libdc24_edge_core.so"
    return EDGE / "target" / "release" / name


def _record_line(path: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"{path},sha256={digest},{len(data)}"


def get_requires_for_build_wheel(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    tag = f"py3-none-{_platform_tag()}"
    target = Path(metadata_directory) / DIST_INFO
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_bytes(_metadata())
    (target / "WHEEL").write_bytes(_wheel(tag))
    return DIST_INFO


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    tag = f"py3-none-{_platform_tag()}"
    native = _native_library()
    entries: dict[str, bytes] = {}
    for source in sorted((ROOT / "src" / PACKAGE).glob("*.py")):
        entries[f"{PACKAGE}/{source.name}"] = source.read_bytes()
    entries[f"{PACKAGE}/{native.name}"] = native.read_bytes()
    entries[f"{DIST_INFO}/METADATA"] = _metadata()
    entries[f"{DIST_INFO}/WHEEL"] = _wheel(tag)
    records = [_record_line(path, data) for path, data in entries.items()]
    records.append(f"{DIST_INFO}/RECORD,,")
    entries[f"{DIST_INFO}/RECORD"] = ("\n".join(records) + "\n").encode("utf-8")
    filename = f"{DISTRIBUTION}-{VERSION}-{tag}.whl"
    destination = Path(wheel_directory) / filename
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for path, data in entries.items():
            wheel.writestr(path, data)
    return filename
