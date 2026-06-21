#!/usr/bin/env python3

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("LC_ALL", None)
    env["LANG"] = "en_US.UTF-8"
    env["LC_CTYPE"] = "en_US.UTF-8"
    if platform.system() == "Darwin":
        path_parts = []
        for candidate in [
            Path("/opt/homebrew/bin"),
            Path.home() / "utils" / "oss-cad-suite" / "bin",
        ]:
            if candidate.is_dir():
                path_parts.append(str(candidate))
        path_parts.extend(["/usr/bin", "/bin", "/usr/sbin", "/sbin"])
        path_parts.append(env.get("PATH", ""))
        env["PATH"] = ":".join(part for part in path_parts if part)
    elif (Path.home() / "utils" / "oss-cad-suite" / "bin").is_dir():
        env["PATH"] = f"{Path.home() / 'utils' / 'oss-cad-suite' / 'bin'}:{env.get('PATH', '')}"
    return env


def parse_filelist(root: Path) -> tuple[list[Path], list[Path]]:
    sources: list[Path] = []
    include_dirs: list[Path] = []
    for raw_line in (root / "filelist.f").read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("+incdir+"):
            include_dirs.append((root / line.removeprefix("+incdir+")).resolve())
            continue
        if line.startswith("-I"):
            include_dirs.append((root / line.removeprefix("-I")).resolve())
            continue
        source = (root / line).resolve()
        if source.name == "stream_arb_fifo.sv":
            continue
        sources.append(source)
    return sources, include_dirs


def build_sby(mode: str, rtl: Path, props: Path, build_dir: Path, depth: int) -> Path:
    sources, include_dirs = parse_filelist(ROOT)
    include_args = " ".join(f"-I{path}" for path in include_dirs)
    source_args = " ".join(str(path) for path in [*sources, rtl.resolve(), props.resolve()])
    sby_mode = "bmc" if mode == "prove" else mode
    build_dir.mkdir(parents=True, exist_ok=True)
    work = build_dir / mode
    shutil.rmtree(work / "job", ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    sby_file = work / "job.sby"
    sby_file.write_text(
        f"""[options]
mode {sby_mode}
depth {depth}

[engines]
smtbmc z3

[script]
read -formal -sv -DBSG_HIDE_FROM_SYNTHESIS {include_args} {source_args}
prep -top stream_arb_fifo_formal_top
""",
        encoding="utf-8",
    )
    return sby_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["prove", "cover"], required=True)
    parser.add_argument("--rtl", type=Path, default=ROOT / "rtl" / "stream_arb_fifo.sv")
    parser.add_argument(
        "--props",
        type=Path,
        default=ROOT / "formal" / "stream_arb_fifo_props.sv",
    )
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build" / "formal")
    parser.add_argument("--depth", type=int, default=12)
    args = parser.parse_args()

    sby_file = build_sby(args.mode, args.rtl, args.props, args.build_dir, args.depth)
    result = subprocess.run(
        ["sby", "-f", sby_file.name],
        cwd=sby_file.parent,
        env=tool_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
