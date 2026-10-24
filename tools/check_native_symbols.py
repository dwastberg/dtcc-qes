#!/usr/bin/env python3
"""Audit undefined symbols in QES archives and bridge objects (not nanobind).

Step 2: --categories file_io io_libraries -- <archives/objects>
Step 3: omit --categories to require the complete audit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

CATEGORIES = ("termination", "console", "file_io", "io_libraries")
TERMINATION = {"exit", "_exit", "_Exit", "quick_exit", "abort", "__assert_fail", "__assert_rtn"}
CONSOLE = {
    "stdout", "stderr", "printf", "vprintf", "puts", "putchar", "fprintf",
    "vfprintf", "fputs", "fputc", "fwrite", "perror", "__stdoutp", "__stderrp",
    "__printf_chk", "__fprintf_chk", "__vprintf_chk", "__vfprintf_chk",
}
FILE_IO = {
    "fopen", "freopen", "open", "open64", "fopen64", "freopen64", "openat",
    "creat", "fdopen", "popen", "read", "write", "stat", "lstat", "access",
}

# No exemptions are needed for step 2. Future platform-specific exemptions
# must name the exact symbol and explain why it cannot perform prohibited I/O.
ALLOWLIST: dict[str, str] = {}


def normalize(symbol: str) -> str:
    symbol = re.sub(r"\bstd::__(?:1|cxx11|ndk1)::", "std::", symbol)
    return re.split(r"[@$]", symbol, maxsplit=1)[0]  # ELF/Mach-O symbol suffix


def categories_for(symbol: str) -> set[str]:
    symbol = normalize(symbol)
    # Mach-O prefixes C symbols with one underscore; preserve real underscores
    # by checking both spellings instead of blindly stripping them all.
    spellings = {symbol, symbol.removeprefix("_")}
    categories = set()
    if spellings & TERMINATION:
        categories.add("termination")
    if spellings & CONSOLE or re.search(r"\bstd::(?:w?cout|w?cerr|w?clog)\b", symbol):
        categories.add("console")
    if spellings & FILE_IO or re.search(r"\bstd::(?:basic_(?:filebuf|ifstream|ofstream|fstream)|filesystem)\b", symbol):
        categories.add("file_io")
    if any(re.match(r"(?:nc_|GDAL|OGR|CPL)", name) for name in spellings) or re.search(r"\b(?:netCDF::|boost::program_options::)", symbol):
        categories.add("io_libraries")
    return categories


def undefined_symbols(path: Path) -> list[str]:
    # -C demangles both libc++ Mach-O and libstdc++ ELF symbols.
    proc = subprocess.run(["nm", "-u", "-C", str(path)], capture_output=True, text=True, check=True)
    symbols = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.endswith(":"):
            continue  # archive/member headings
        line = re.sub(r"^(?:[0-9a-fA-F]+\s+)?[Uuwv]\s+", "", line)
        symbols.append(line)
    return symbols


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--categories", nargs="+", choices=CATEGORIES, default=list(CATEGORIES))
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failures = []
    for path in args.paths:
        for symbol in undefined_symbols(path):
            categories = categories_for(symbol) & set(args.categories)
            if categories and normalize(symbol) not in ALLOWLIST:
                failures.append(f"{path}: {', '.join(sorted(categories))}: {symbol}")
    if failures:
        parser.exit(1, "Native symbol audit failed:\n" + "\n".join(failures) + "\n")
    print(f"Native symbol audit passed ({', '.join(args.categories)}; {len(args.paths)} inputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
