#!/usr/bin/env bash
# setup.sh — rewrite program.md with the current machine's Python path and repo root.
#
# Usage:
#   ./setup.sh                  # auto-detect python from $PATH / active env
#   ./setup.sh /path/to/python  # use a specific interpreter
#
# Idempotent: safe to re-run. Replaces the two "Environment" lines in program.md.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRAM_MD="$REPO_ROOT/program.md"

if [[ ! -f "$PROGRAM_MD" ]]; then
  echo "error: program.md not found at $PROGRAM_MD" >&2
  exit 1
fi

# 1. Resolve python interpreter
if [[ $# -ge 1 ]]; then
  PYTHON_BIN="$1"
elif [[ -n "${CONDA_PREFIX:-}" && -x "$CONDA_PREFIX/bin/python" ]]; then
  PYTHON_BIN="$CONDA_PREFIX/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi

if [[ -z "${PYTHON_BIN:-}" || ! -x "$PYTHON_BIN" ]]; then
  echo "error: could not find a python interpreter. Pass one explicitly: ./setup.sh /path/to/python" >&2
  exit 1
fi

# 2. Sanity-check that this python can import the backtester
if ! "$PYTHON_BIN" -c "import sys; sys.path.insert(0, '$REPO_ROOT'); import backtester" 2>/dev/null; then
  echo "warning: $PYTHON_BIN cannot import 'backtester' from $REPO_ROOT" >&2
  echo "         install requirements first:  $PYTHON_BIN -m pip install -r requirements.txt" >&2
fi

echo "repo root  : $REPO_ROOT"
echo "python bin : $PYTHON_BIN"

# 3. Rewrite the two Environment lines in program.md.
#    We match by the leading bullet text, not the old value, so this is idempotent.
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# Use python (already required) to do the in-place edit — avoids sed escaping headaches with slashes.
"$PYTHON_BIN" - "$PROGRAM_MD" "$PYTHON_BIN" "$REPO_ROOT" > "$TMP" <<'PY'
import re, sys
path, py_bin, repo_root = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    text = f.read()

text = re.sub(
    r'(- \*\*Python executable\*\*:\s*)`[^`]*`',
    lambda m: f"{m.group(1)}`{py_bin}`",
    text,
)
text = re.sub(
    r'(- \*\*Repository root\*\*:\s*)`[^`]*`',
    lambda m: f"{m.group(1)}`{repo_root}`",
    text,
)
# Also rewrite any inline run-command examples that hardcode the old python path.
text = re.sub(
    r'`/[^`]*/bin/python(\s+[^`]*)?`',
    lambda m: f"`{py_bin}{m.group(1) or ''}`",
    text,
)
sys.stdout.write(text)
PY

mv "$TMP" "$PROGRAM_MD"
trap - EXIT

echo "program.md updated."
