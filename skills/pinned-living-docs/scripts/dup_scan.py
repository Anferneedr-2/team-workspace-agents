#!/usr/bin/env python3
"""Scan a doc tree for long lines shared across .md files — evidence for a duplication audit.

Usage: python3 dup_scan.py [root] [min_len]

Interpreting the result:
  benign    template boilerplate instantiated per project (banner, placeholder line, isolation pointer)
  not benign the same FACT maintained in two files (roster row, scoping rule, changelog entry)
             — that is a second source of truth waiting to drift; replace one copy with a link.
"""

import sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
min_len = int(sys.argv[2]) if len(sys.argv) > 2 else 90

files = sorted(root.rglob("*.md"))
seen = defaultdict(set)
for f in files:
    for line in f.read_text().splitlines():
        s = line.strip()
        # table rows, bullets and headings are structure/templates, not prose facts
        if len(s) <= min_len or s.startswith(("|", "-", "#", "```")):
            continue
        seen[s].add(str(f.relative_to(root)))

shared = {k: v for k, v in seen.items() if len(v) > 1}
print(f"{len(files)} md files; {len(seen)} long prose lines; {len(shared)} shared across files")
for text, owners in sorted(shared.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    print(f"\n  [{', '.join(sorted(owners))}]\n    {text[:180]}")
