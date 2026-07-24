#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Video Downloader — macOS .app ビルドスクリプト
#
#  dist/VideoDownloader.app を生成します。開発者向け。
#  普通に「使うだけ」なら run_mac.command をダブルクリックしてください。
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

# tkinter が使える Python を選ぶ（run_mac.command と同じ方針）
pick_python() {
  for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import tkinter" >/dev/null 2>&1; then
      echo "$cand"; return 0
    fi
  done
  return 1
}
PY="$(pick_python || true)"
if [ -z "${PY:-}" ]; then
  echo "✖ tkinter が使える Python が必要です。 brew install python-tk を実行してください。"
  exit 1
fi
echo "▶ Python: $PY"

# ビルド用の仮想環境
VENV=".venv-build"
[ -d "$VENV" ] || "$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet --upgrade yt-dlp pyinstaller

# アイコン生成（best-effort）
echo "▶ アイコンを生成中..."
python make_icns.py || echo "  （アイコン生成に失敗。デフォルトアイコンで続行します）"

# ビルド
echo "▶ .app をビルド中..."
python -m PyInstaller VideoDownloader-mac.spec --noconfirm

echo ""
echo "✔ 完了: dist/VideoDownloader.app"
echo "  初回起動時、未署名アプリのため Gatekeeper に止められた場合は"
echo "  右クリック →「開く」、または以下を実行してください:"
echo "    xattr -dr com.apple.quarantine dist/VideoDownloader.app"
