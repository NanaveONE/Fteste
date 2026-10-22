#!/usr/bin/env python3
"""Fail fast if the *host* ReXGlue toolchain lacks required C++23 facilities.

Linux/Ubuntu 24.04 Clang 18 + libstdc++ hides std::expected because its
__cpp_concepts macro is 201907L. Clang 19 implements 202002L. Verify actual
compile+link+execution rather than relying only on the compiler's version.
This script never reads private Fable II files.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MINIMUM_CLANG_MAJOR = 19

CPP23_SMOKE = r'''#include <charconv>
#include <cmath>
#include <expected>
#include <string>
#include <thread>
#include <vector>

#if !defined(__cpp_concepts) || __cpp_concepts < 202002L
#error Clang concepts support is too old for libstdc++ std::expected
#endif
#if !defined(__cpp_lib_expected) || __cpp_lib_expected < 202202L
#error libstdc++ std::expected is not enabled
#endif
#if __cplusplus < 202100L
#error C++23 mode is required
#endif
int main() {
    std::expected<std::vector<int>, std::string> success(std::vector<int>{42});
    if (!success || success->at(0) != 42) return 1;
    std::expected<int, std::string> failure = std::unexpected(std::string("expected error"));
    if (failure || failure.error() != "expected error") return 2;
    float number = 0.0f;
    constexpr char input[] = "1.25";
    auto result = std::from_chars(input, input + 4, number, std::chars_format::general);
    if (result.ec != std::errc{} || result.ptr != input + 4 || number != 1.25f) return 3;
    std::jthread thread([] {});
    thread.join();
    return 0;
}
'''


def clang_major(version_line: str) -> int:
    match = re.search(r'\bclang version\s+(\d+)\b', version_line, re.I)
    if not match:
        raise ValueError('Tool is not Clang: ' + version_line.splitlines()[0][:160])
    return int(match.group(1))


def command_result(argv: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f'Unable to execute {argv[0]}: {e}') from e


def verify_toolchain(cc: str = 'clang-19', cxx: str = 'clang++-19') -> str:
    for exe in [cc, cxx]:
        if shutil.which(exe) is None:
            raise ValueError(f'Missing {exe}; install Ubuntu 24.04 clang-19')
        version = command_result([exe, '--version'])
        if version.returncode != 0:
            raise ValueError(f'Cannot run {exe}: {version.stderr.strip()}')
        major = clang_major(version.stdout)
        if major < MINIMUM_CLANG_MAJOR:
            raise ValueError(f'{exe} is Clang {major}; Clang >= {MINIMUM_CLANG_MAJOR} is required for std::expected')

    with tempfile.TemporaryDirectory(prefix='fable2-cpp23-') as tmp:
        source = Path(tmp) / 'check.cpp'
        program = Path(tmp) / 'check'
        source.write_text(CPP23_SMOKE, encoding='utf-8')
        compile_result = command_result([
            cxx, '-std=c++23', '-O2', '-pthread', '-march=x86-64-v2',
            '-fno-char8_t', str(source), '-o', str(program),
        ])
        if compile_result.returncode != 0:
            raise ValueError('C++23 compile/link check failed: ' +
                             (compile_result.stderr or compile_result.stdout)[-7000:])
        run = command_result([str(program)], timeout=15)
        if run.returncode != 0:
            raise ValueError(f'C++23 executable smoke check failed (exit={run.returncode}): '
                             + (run.stderr or run.stdout)[-1000:])
    return f'PASS: host {cxx} supports std::expected, std::unexpected, floating from_chars and jthread'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang-19')
    parser.add_argument('--cxx', default='clang++-19')
    args = parser.parse_args()
    try:
        print(verify_toolchain(args.cc, args.cxx))
        return 0
    except ValueError as e:
        print(f'BLOCKED: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
