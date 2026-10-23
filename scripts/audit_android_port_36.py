#!/usr/bin/env python3
"""Audit reachable host sources in an isolated Android Fable II worktree.

This is a preflight *heuristic*, not a C++ compiler or a guarantee of linkage.
The generated guest translation units are deliberately outside its scope.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

BAD_HEADERS = re.compile(r'^(windows\.h|process\.h|intrin\.h|io\.h|share\.h|d3d\w*\.h|dxgi\w*\.h)$', re.I)
BAD_APIS = re.compile(r'\b(?:VirtualAlloc|VirtualQuery|VirtualProtect|CreateThread|WaitForSingleObjectEx|CreateFileA|GetAsyncKeyState|Sleep|__try|__except|__declspec)\b')
DIRECTIVE = re.compile(r'^\s*#\s*(if|ifdef|ifndef|elif|else|endif|include)\b(.*)$')
INCLUDE = re.compile(r'^\s*[<"]([^>"]+)[>"]')
DEF = re.compile(r'defined\s*(?:\(\s*([A-Za-z_]\w*)\s*\)|\s+([A-Za-z_]\w*))')
MACROS = {'_WIN32': False, 'WIN32': False, '__ANDROID__': True, 'ANDROID': True,
          'FABLE2_REMOTE_CONTROL': False}


def condition(expr: str) -> bool | None:
    """Known platform guards; return None for other (unknown) C++ conditions."""
    expr = re.sub(r'//.*', '', expr).strip()
    def replace(m):
        key = m.group(1) or m.group(2)
        return str(int(MACROS[key])) if key in MACROS else 'UNKNOWN'
    expr = DEF.sub(replace, expr)
    for key, value in MACROS.items():
        expr = re.sub(r'\b' + re.escape(key) + r'\b', str(int(value)), expr)
    expr = re.sub(r'\b(true|false)\b', lambda m: '1' if m[0] == 'true' else '0', expr)
    if re.search(r'[^\s01!&|()]', expr):
        return None
    if not re.fullmatch(r'[\s01!&|()]+', expr):
        return None
    python_expr = expr.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ')
    try:
        return bool(eval(python_expr, {'__builtins__': {}}, {}))
    except (SyntaxError, ValueError, TypeError):
        return None


def scan(root: Path) -> dict:
    src = root / 'src'
    sources = list(src.rglob('*.cpp'))
    sources = [p for p in sources if p.name != 'vulkan_smoke.cpp']
    if not sources:
        raise ValueError('No Fable II host C++ sources in worktree/src')
    include_roots = (src, src/'core', src/'diagnostics', src/'input', root)
    visited = set()
    problems: list[dict] = []
    warnings: list[dict] = []

    def visit(file: Path) -> None:
        file = file.resolve()
        if file in visited or not file.is_file():
            return
        visited.add(file)
        # Each frame stores parent activity, branch condition and whether a
        # prior alternative has matched. Unknown expressions are checked as
        # possible active paths and reported as warnings only.
        frames: list[tuple[bool, bool | None, bool | None]] = []
        active = True
        uncertain = False
        # local uncertainty per frame, not inherited through a later #endif.
        unsure_stack: list[bool] = []
        for lineno, line in enumerate(file.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            m = DIRECTIVE.match(line)
            if m and m[1] in ('if','ifdef','ifndef'):
                typ, arg = m[1], m[2].strip()
                if typ == 'ifdef': c = MACROS.get(arg)
                elif typ == 'ifndef':
                    known = MACROS.get(arg)
                    c = not known if known is not None else None
                else: c = condition(arg)
                frames.append((active, c, c))
                unsure_stack.append(uncertain)
                active = active and c is not False
                uncertain = uncertain or (c is None)
                continue
            if m and m[1] in ('else','elif') and frames:
                parent, prior, first = frames[-1]
                alt = (not prior) if prior is not None else None
                if m[1] == 'elif':
                    extra = condition(m[2].strip())
                    alt = alt and extra if alt is not None and extra is not None else None
                frames[-1] = (parent, (prior or alt) if prior is not None and alt is not None else None, first)
                active = parent and alt is not False
                uncertain = unsure_stack[-1] or alt is None
                continue
            if m and m[1] == 'endif' and frames:
                active = frames.pop()[0]
                uncertain = unsure_stack.pop()
                continue
            if not active or not m or m[1] != 'include':
                continue
            item = INCLUDE.match(m[2].strip())
            if item is None:
                continue
            header = item[1]
            if BAD_HEADERS.fullmatch(Path(header).name):
                problem = {'file': file.relative_to(root).as_posix(), 'line': lineno, 'include': header}
                (warnings if uncertain else problems).append(problem)
            if m[2].strip().startswith('"'):
                targets = (file.parent/header, *(p/header for p in include_roots))
                for t in targets:
                    if t.is_file() and t.resolve().is_relative_to(root.resolve()):
                        visit(t)
                        break
    for file in sorted(sources):
        visit(file)
    return {'host_cpp': len(sources), 'files_inspected': len(visited),
            'unguarded_windows_headers': problems, 'conditionally_suspect_headers': warnings,
            'note': 'Host-source header audit only; build/link/runtime checks remain required.'}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--worktree', type=Path, required=True)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--strict', action='store_true')
    args = ap.parse_args()
    result = scan(args.worktree.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(f"[preflight36] Inspected {result['files_inspected']} host sources/headers ({result['host_cpp']} C++ units)")
    for x in result['unguarded_windows_headers']:
        print(f"[preflight36] ERROR {x['file']}:{x['line']} includes {x['include']} on Android")
    for x in result['conditionally_suspect_headers']:
        print(f"[preflight36] WARNING {x['file']}:{x['line']} may include {x['include']}")
    if args.strict and result['unguarded_windows_headers']:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
