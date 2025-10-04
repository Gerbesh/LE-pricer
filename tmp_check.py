import pathlib
path = pathlib.Path(r"F:/Pricer/worker.py")
for line in path.read_text(encoding="utf-8").splitlines():
    if '"' in line and '\\' not in line and 'self._log' not in line and 'Template' not in line and 'format' not in line:
        if any(ord(ch) > 127 for ch in line):
            print(repr(line))
