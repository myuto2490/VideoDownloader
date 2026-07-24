#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Video Downloader — macOS ランチャー
#
#  この .command ファイルを Finder で「ダブルクリック」するだけで、
#  必要なもの（Python 依存関係・ffmpeg）を自動で用意してアプリを起動します。
#
#  初回だけ数分かかります（yt-dlp / ffmpeg の取得）。2回目以降はすぐ起動します。
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# このスクリプトがあるフォルダへ移動（ダブルクリック時の作業ディレクトリ対策）
cd "$(dirname "$0")"

echo "======================================================"
echo "  Video Downloader (macOS)"
echo "======================================================"

# ── 1. 使う Python を決める ─────────────────────────────
#   GUI(tkinter) が動く Python を優先。Homebrew の python-tk があれば
#   新しい Tk 8.6 で見た目もきれいになる。無ければシステム python3 を使う。
pick_python() {
  for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import tkinter" >/dev/null 2>&1; then
      echo "$cand"
      return 0
    fi
  done
  return 1
}

PY="$(pick_python || true)"

if [ -z "${PY:-}" ]; then
  # tkinter が使える Python が無い → Homebrew があれば python-tk を入れる
  if command -v brew >/dev/null 2>&1; then
    echo "▶ GUI 表示に必要な python-tk をインストールします（初回のみ）..."
    brew install python-tk || true
    PY="$(pick_python || true)"
  fi
fi

if [ -z "${PY:-}" ]; then
  echo "✖ tkinter が使える Python が見つかりませんでした。"
  echo "  Homebrew を入れて  brew install python-tk  を実行してください。"
  echo "  Homebrew: https://brew.sh"
  echo ""
  read -r -p "Enter キーで終了します。" _ || true
  exit 1
fi
echo "▶ 使用する Python: $PY  ($("$PY" -c 'import sys;print(sys.version.split()[0])'))"

# ── 2. ffmpeg を用意（動画の結合・MP3変換に必要）──────────
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "▶ ffmpeg をインストールします（初回のみ）..."
    brew install ffmpeg || echo "  （brew での ffmpeg 導入に失敗。アプリ内の自動取得に任せます）"
  else
    echo "▶ ffmpeg が無いため、アプリ起動後に自動ダウンロードします。"
  fi
fi

# ── 3. 仮想環境を用意して yt-dlp を入れる ────────────────
VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "▶ 仮想環境を作成します（初回のみ）..."
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "▶ yt-dlp を最新版に更新中..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet --upgrade yt-dlp

# ── 4. 起動 ──────────────────────────────────────────────
echo "▶ アプリを起動します。"
echo "======================================================"
exec python video_downloader.py
