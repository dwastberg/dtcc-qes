"""Build the isolated probe using an existing Unix Makefiles study build.

Reuses that build's bridge objects/libraries and records their fingerprints.
The historical study executable, sources and CMake configuration are untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(build_dir, output):
    root = Path(__file__).resolve().parents[1]
    build_dir, output = build_dir.resolve(), output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    target = build_dir / "CMakeFiles/vertical_grid_study.dir"
    flags = {}
    for line in (target / "flags.make").read_text().splitlines():
        if line.startswith("CXX_") and " = " in line:
            name, value = line.split(" = ", 1)
            flags[name] = shlex.split(value)
    link = shlex.split((target / "link.txt").read_text())
    obj = output.with_suffix(".o")
    compile_command = [link[0], *flags["CXX_DEFINES"], *flags["CXX_INCLUDES"],
                       *flags["CXX_FLAGS"], "-c", str(root / "tools/near_wall_probe.cpp"), "-o", str(obj)]
    subprocess.run(compile_command, cwd=build_dir, check=True)
    original = "CMakeFiles/vertical_grid_study.dir/tools/vertical_grid_study.cpp.o"
    link[link.index(original)] = str(obj)
    link[link.index("-o") + 1] = str(output)
    dependencies = {}
    for arg in link[1:]:
        path = Path(arg) if Path(arg).is_absolute() else build_dir / arg
        if arg != str(output) and path.is_file():
            dependencies[str(path)] = digest(path)
    subprocess.run(link, cwd=build_dir, check=True)
    record = dict(compile_command=compile_command, link_command=link,
                  linked_files_sha256=dependencies, executable_sha256=digest(output))
    output.with_suffix(".build.json").write_text(json.dumps(record, indent=2)+"\n")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.build_dir, args.output)
