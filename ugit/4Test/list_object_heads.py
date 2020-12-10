#!/usr/bin/env python3

# list heads of all object files in .ugit/objects

from pathlib import Path

p = Path ('.ugit/objects')

for f in (fp for fp in p.rglob('*') if fp.is_file() if fp.is_file()):
     print(f.name, '\t', f.read_bytes()[0:20])


