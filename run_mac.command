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

# macOS システム Tk 8.5 の非推奨警告を抑止
export TK_SILENCE_DEPRECATION=1

echo "======================================================"
echo "  Video Downloader (macOS)"
echo "======================================================"

# 候補の Python 一覧（新しい Homebrew 版を優先）
CANDIDATES=(
  /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11
  /opt/homebrew/bin/python3 /usr/local/bin/python3 python3
)

# tkinter が import でき、かつ Tk が ver 以上か
_tk_ok() { "$1" -c 'import tkinter' >/dev/null 2>&1; }
_tk_modern() { "$1" -c 'import sys,tkinter; sys.exit(0 if tkinter.TkVersion>=8.6 else 1)' >/dev/null 2>&1; }

# ── 1. 使う Python を決める ─────────────────────────────
#   新しい Tk 8.6 が使える Python を最優先。無ければシステムの Tk 8.5 でも
#   起動します（非推奨警告は抑止済み・動作に問題はありません）。
PY=""
for c in "${CANDIDATES[@]}"; do
  command -v "$c" >/dev/null 2>&1 || continue
  if _tk_ok "$c" && _tk_modern "$c"; then PY="$c"; break; fi
done
TK85_FALLBACK=0
if [ -z "$PY" ]; then
  for c in "${CANDIDATES[@]}"; do
    command -v "$c" >/dev/null 2>&1 || continue
    if _tk_ok "$c"; then PY="$c"; TK85_FALLBACK=1; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "✖ GUI(tkinter) が使える Python が見つかりませんでした。"
  echo "  Homebrew を入れて  brew install python-tk  を実行してください（https://brew.sh）。"
  read -r -p "Enter キーで終了します。" _ || true
  exit 1
fi
if [ "$TK85_FALLBACK" = "1" ]; then
  echo "  （ヒント: brew install python-tk を入れると、より新しい見た目の GUI になります）"
fi
PYVER="$("$PY" -c 'import sys,tkinter;print(sys.version.split()[0], "/ Tk", tkinter.TkVersion)')"
echo "▶ 使用する Python: $PY  ($PYVER)"

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
# 既存 venv が別バージョンの Python（＝古い Tk）で作られていたら作り直す
if [ -d "$VENV" ]; then
  WANT="$("$PY" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null || echo x)"
  HAVE="$("$VENV/bin/python" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null || echo y)"
  if [ "$WANT" != "$HAVE" ]; then
    echo "▶ Python が変わったため仮想環境を作り直します（$HAVE → $WANT）..."
    rm -rf "$VENV"
  fi
fi
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
echo "▶ アプリを起動します。ウィンドウが前面に表示されます。"
echo "======================================================"
exec python video_downloader.py
