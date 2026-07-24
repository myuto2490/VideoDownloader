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

APP="dist/VideoDownloader.app"

# 自己署名（ad-hoc）。配布用の署名ではないが、これがないと Apple Silicon で
# 「壊れているため開けません」と言われることがある。
echo "▶ ad-hoc 署名中..."
xattr -cr "$APP" || true
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 \
  && echo "  署名しました" || echo "  （署名に失敗。そのまま続行します）"

echo ""
echo "✔ 完了: $APP"

# --install で /Applications へインストール
if [ "${1:-}" = "--install" ]; then
  echo "▶ /Applications へインストール中..."
  rm -rf "/Applications/VideoDownloader.app"
  cp -R "$APP" /Applications/
  xattr -cr "/Applications/VideoDownloader.app" || true
  echo "✔ インストール完了: /Applications/VideoDownloader.app"
  echo "  Launchpad / Spotlight から「VideoDownloader」で起動できます。"
else
  echo "  /Applications に入れるには:  ./build_mac.sh --install"
  echo "  Gatekeeper に止められた場合は 右クリック →「開く」、または:"
  echo "    xattr -dr com.apple.quarantine $APP"
fi
