"""Stage an explicit runtime payload; never commit, publish, or install it."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--output", required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
out = Path(a.output).resolve()
if out.exists():
    raise SystemExit("Output already exists; choose a fresh directory to preserve prior review artifacts")
if root == out or root in out.parents:
    raise SystemExit("Stage outside the source checkout")
files = [root / name for name in ("plugin.yaml", "__init__.py", "README.md", "LICENSE", "CHANGELOG.md")]
files.append(root / "scripts" / "configure.py")
for folder, extensions in [
    ("watchdog", {".py"}),
    ("desktop", {".js"}),
    ("dashboard", {".py", ".json"}),
    ("docs", {".md", ".jpg", ".txt"}),
    ("assets", {".png"}),
]:
    files.extend(p for p in sorted((root / folder).rglob("*")) if p.is_file() and p.suffix in extensions)
if len(files) > 64:
    raise SystemExit("Runtime payload exceeds 64-file review bound")
out.mkdir(parents=True)
manifest = []
for source in files:
    target = out / source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    manifest.append({"path": str(source.relative_to(root)), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
(out.parent / (out.name + "-manifest.json")).write_text(json.dumps(manifest, indent=2) + "\n")
print(f"Staged {len(files)} files in {out}")
