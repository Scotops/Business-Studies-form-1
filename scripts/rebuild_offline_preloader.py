"""Rebuild the generated inline data cache used by the offline ADT reader."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRELOADER_PATH = ROOT / "assets/offline-preloader.js"
START_MARKER = "  var INLINE = "
END_MARKER = ";\n  var BASE_DIR"
EXTRA_INLINE_PATHS = ("./content/pdf-word-positions.json",)


source = PRELOADER_PATH.read_text(encoding="utf-8")
match = re.search(
    re.escape(START_MARKER) + r"(.*?)" + re.escape(END_MARKER),
    source,
    flags=re.DOTALL,
)
if not match:
    raise RuntimeError("Could not locate the generated INLINE payload")

old_payload = json.loads(match.group(1))
new_payload: dict[str, object] = {}

source_keys = list(old_payload)
for key in EXTRA_INLINE_PATHS:
    if key not in source_keys:
        source_keys.append(key)

for key in source_keys:
    relative = key[2:] if key.startswith("./") else key
    file_path = ROOT / relative
    if not file_path.is_file():
        raise FileNotFoundError(f"Inline source is missing: {file_path}")
    if file_path.suffix.lower() == ".json":
        new_payload[key] = json.loads(file_path.read_text(encoding="utf-8"))
    else:
        new_payload[key] = file_path.read_text(encoding="utf-8")

encoded = json.dumps(new_payload, ensure_ascii=False, separators=(",", ":"))
rebuilt = source[: match.start(1)] + encoded + source[match.end(1) :]
PRELOADER_PATH.write_text(rebuilt, encoding="utf-8", newline="\n")
print(f"Rebuilt {PRELOADER_PATH.name} from {len(new_payload)} current source files")
