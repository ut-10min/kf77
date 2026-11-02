#!/bin/zsh
# macOS: ダブルクリックで変換画面を起動する。
SCRIPT_DIR="${0:A:h}"
SITE_DIR="${SCRIPT_DIR:h:h}"
for PYTHON_CANDIDATE in "$SITE_DIR/.venv/bin/python" \
  "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" \
  "$(command -v python3)"; do
  if [[ -x "$PYTHON_CANDIDATE" ]] && "$PYTHON_CANDIDATE" -c 'import openpyxl, pdfplumber' >/dev/null 2>&1; then
    exec "$PYTHON_CANDIDATE" "$SCRIPT_DIR/web.py" --open-browser
  fi
done
print '必要なPythonライブラリがありません。scripts/import_data/README.md の「最初の準備」を実行してください。'
read '?Enterで閉じます。'
