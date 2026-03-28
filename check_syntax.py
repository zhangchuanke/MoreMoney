import ast
import pathlib

root = pathlib.Path(r"E:\Project\py\Agent\MoreMoney")
skip = {"venv", "__pycache__", ".idea", ".git"}

errors = []
checked = 0

for p in sorted(root.rglob("*.py")):
    if any(s in p.parts for s in skip):
        continue
    checked += 1
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"  {p.relative_to(root)}: line {e.lineno} - {e.msg}")

if errors:
    print(f"Found {len(errors)} error(s) in {checked} files:")
    for err in errors:
        print(err)
else:
    print(f"All {checked} files OK - no syntax errors.")
