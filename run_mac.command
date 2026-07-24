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

# 候補の Python 一覧（新しい Homebrew 版を優先して自動探索）
CANDIDATES=()
for p in $(ls /opt/homebrew/bin/python3.1* /usr/local/bin/python3.1* 2>/dev/null | sort -Vr); do
  CANDIDATES+=("$p")
done
CANDIDATES+=(/opt/homebrew/bin/python3 /usr/local/bin/python3 python3)

# tkinter が import でき、かつ Tk が ver 以上か
_tk_ok() { "$1" -c 'import tkinter' >/dev/null 2>&1; }
_tk_modern() { "$1" -c 'import sys,tkinter; sys.exit(0 if tkinter.TkVersion>=8.6 else 1)' >/dev/null 2>&1; }

# ── 1. 使う Python を決める ─────────────────────────────
#   新しい Tk（8.6 以上）が使える Python が必要。
#   ※ macOS 標準の Tk 8.5 は最近の macOS でウィンドウが真っ黒になる不具合が
#     あるため使わない。無ければ Homebrew の python-tk を導入する。
find_modern_py() {
  for c in "${CANDIDATES[@]}"; do
    command -v "$c" >/dev/null 2>&1 || continue
    if _tk_ok "$c" && _tk_modern "$c"; then echo "$c"; return 0; fi
  done
  return 1
}

PY="$(find_modern_py || true)"
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "▶ GUI 表示に必要な新しい Tk (python-tk) をインストールします（初回のみ・数分）..."
    brew install python-tk || true
    # インストールで増えた versioned python を再探索
    CANDIDATES=()
    for p in $(ls /opt/homebrew/bin/python3.1* /usr/local/bin/python3.1* 2>/dev/null | sort -Vr); do
      CANDIDATES+=("$p")
    done
    CANDIDATES+=(/opt/homebrew/bin/python3 /usr/local/bin/python3 python3)
    PY="$(find_modern_py || true)"
  fi
fi
if [ -z "$PY" ]; then
  echo "✖ 新しい Tk が使える Python が見つかりませんでした。"
  echo "  Homebrew を入れて  brew install python-tk  を実行してください（https://brew.sh）。"
  echo "  （macOS 標準の Tk 8.5 はウィンドウが真っ黒になるため使用できません）"
  read -r -p "Enter キーで終了します。" _ || true
  exit 1
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
