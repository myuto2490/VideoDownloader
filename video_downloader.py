from __future__ import annotations   # Python 3.9 でも `str | None` 注釈を使えるように

import os
# macOS のシステム Tk 8.5 の非推奨警告を抑止（tkinter を import する前に設定する）
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox
import importlib.abc
import importlib.machinery
import threading
import subprocess
import sys
import io
import json
import shutil
import traceback
import zipfile
import urllib.request
from datetime import datetime

APP_VERSION = "1.1.0"

# ──────────────────────────────────────────────────────
#  Platform detection  (Windows / macOS / Linux 共通化)
# ──────────────────────────────────────────────────────
_IS_WIN = sys.platform == "win32"
_IS_MAC = sys.platform == "darwin"
_IS_LINUX = not _IS_WIN and not _IS_MAC

# 実行ファイル名（Windows は .exe）
FFMPEG_BIN = "ffmpeg.exe" if _IS_WIN else "ffmpeg"
FFPROBE_BIN = "ffprobe.exe" if _IS_WIN else "ffprobe"


# ──────────────────────────────────────────────────────
#  libs/ setup  (exeと同じフォルダの libs/ を優先ロード)
# ──────────────────────────────────────────────────────
def _get_base_dir() -> str:
    """実行ファイル（exeまたは.py）があるディレクトリを返す。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


_LIBS_DIR = os.path.join(_get_base_dir(), "libs")
os.makedirs(_LIBS_DIR, exist_ok=True)

if _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)   # libs/ 内の yt-dlp を優先


class _LibsYtdlpFinder(importlib.abc.MetaPathFinder):
    """PyInstaller の FrozenImporter は sys.path を無視して exe 内蔵の
    yt_dlp を読み込んでしまうため、libs/yt_dlp が存在するときは
    このファインダーを sys.meta_path の先頭に置いて libs/ 側を優先させる。"""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "yt_dlp" and not fullname.startswith("yt_dlp."):
            return None
        search = [_LIBS_DIR] if fullname == "yt_dlp" else path
        return importlib.machinery.PathFinder.find_spec(fullname, search)


if os.path.isdir(os.path.join(_LIBS_DIR, "yt_dlp")):
    sys.meta_path.insert(0, _LibsYtdlpFinder())


def _import_ytdlp():
    try:
        import yt_dlp as m
        src = "libs" if (getattr(m, "__file__", "") or "").startswith(_LIBS_DIR) else "bundled"
        return m, src
    except Exception:
        # libs/ のコピーが壊れている場合は libs 優先を外して内蔵版で再試行
        sys.meta_path[:] = [f for f in sys.meta_path
                            if not isinstance(f, _LibsYtdlpFinder)]
        for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
            del sys.modules[name]
        try:
            import yt_dlp as m
            return m, "bundled"
        except Exception:
            return None, "none"


yt_dlp, _YTDLP_SOURCE = _import_ytdlp()


# ──────────────────────────────────────────────────────
#  Config persistence
# ──────────────────────────────────────────────────────
OUTPUT_DIR_KEY = "output_dir"
OPEN_AFTER_KEY = "open_after"
OPTS_COLLAPSED_KEY = "opts_collapsed"
_config: dict = {}


def _load_config():
    path = os.path.join(_get_base_dir(), ".vd_config")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    _config[k.strip()] = v.strip()


def _save_config():
    path = os.path.join(_get_base_dir(), ".vd_config")
    with open(path, "w", encoding="utf-8") as f:
        for k, v in _config.items():
            f.write(f"{k}={v}\n")


# ──────────────────────────────────────────────────────
#  yt-dlp updater (PyPI wheel 直接ダウンロード方式)
# ──────────────────────────────────────────────────────
_PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
_UA = f"VideoDownloader/{APP_VERSION} (yt-dlp-updater)"


def _ver_tuple(v: str):
    """'2026.07.04' と '2026.7.4' を同一視できるよう数値タプル化する。"""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return None


def _same_version(a: str | None, b: str | None) -> bool:
    ta, tb = _ver_tuple(a), _ver_tuple(b)
    if ta is not None and tb is not None:
        return ta == tb
    return a == b


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _download_latest_ytdlp(libs_dir: str) -> tuple[str | None, str]:
    """
    PyPI から最新 yt-dlp wheel を libs_dir に展開する。
    戻り値: (旧バージョン, 新バージョン)  既に最新なら新バージョンのみ返す。
    """
    data = _fetch_json(_PYPI_URL)
    latest = data["info"]["version"]

    current = getattr(yt_dlp.version, "__version__", None) if yt_dlp else None
    if _same_version(current, latest):
        return None, latest  # already up-to-date

    # none-any wheel (pure Python) を探す
    wheel_url = None
    for f in data["releases"][latest]:
        if f["filename"].endswith("-py3-none-any.whl") or "none-any" in f["filename"]:
            wheel_url = f["url"]
            break
    if not wheel_url:
        raise RuntimeError("対応するホイールが PyPI に見つかりませんでした。")

    req = urllib.request.Request(wheel_url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        wheel_bytes = r.read()

    # 旧 yt_dlp ディレクトリを削除
    old_dir = os.path.join(libs_dir, "yt_dlp")
    if os.path.isdir(old_dir):
        shutil.rmtree(old_dir)

    # wheel は zip。yt_dlp/ パッケージだけ展開する
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as z:
        for member in z.namelist():
            if member.startswith("yt_dlp/"):
                z.extract(member, libs_dir)

    return current, latest


# ──────────────────────────────────────────────────────
#  ffmpeg auto-setup
#    Windows : yt-dlp 公式ビルド（ffmpeg + ffprobe 同梱）
#    macOS   : evermeet.cx の静的ビルド（ffmpeg / ffprobe を個別取得）
# ──────────────────────────────────────────────────────
# Windows 用（1つの zip に ffmpeg.exe / ffprobe.exe が入っている）
_FFMPEG_URL_WIN = ("https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/"
                   "download/ffmpeg-master-latest-win64-gpl.zip")
# macOS 用（バイナリごとに zip が分かれている静的ビルド）
_FFMPEG_URL_MAC = "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
_FFPROBE_URL_MAC = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"


def _find_ffmpeg() -> str | None:
    """アプリ同梱 → libs/ffmpeg/ → PATH（Homebrew 等）の順で ffmpeg を探す。"""
    base = _get_base_dir()
    for c in (os.path.join(base, FFMPEG_BIN),
              os.path.join(_LIBS_DIR, "ffmpeg", FFMPEG_BIN)):
        if os.path.isfile(c):
            return c
    return shutil.which("ffmpeg")


def _strip_quarantine(path: str):
    """macOS の Gatekeeper 隔離属性を外し、実行できるようにする。"""
    if not _IS_MAC:
        return
    try:
        subprocess.run(["xattr", "-d", "com.apple.quarantine", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _download_and_extract(url: str, dest: str, wanted: set[str],
                          progress=None, base_pct=0.0, span=100.0):
    """url の zip をダウンロードし、basename が wanted に含まれるメンバーを
    dest に展開する。macOS では実行権限付与＋隔離解除も行う。"""
    tmp = os.path.join(dest, "_dl.zip")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(base_pct + done / total * span)
    try:
        with zipfile.ZipFile(tmp) as z:
            for m in z.namelist():
                name = os.path.basename(m)
                if name in wanted:
                    out_path = os.path.join(dest, name)
                    with z.open(m) as src, open(out_path, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if not _IS_WIN:
                        os.chmod(out_path, 0o755)
                        _strip_quarantine(out_path)
    finally:
        os.remove(tmp)


def _download_ffmpeg(progress=None) -> str:
    """ffmpeg / ffprobe を libs/ffmpeg/ にダウンロード・展開する。
    progress には 0-100 の float が渡される。"""
    dest = os.path.join(_LIBS_DIR, "ffmpeg")
    os.makedirs(dest, exist_ok=True)

    if _IS_MAC:
        # evermeet はバイナリごとに zip が分かれているので2回に分けて取得
        _download_and_extract(_FFMPEG_URL_MAC, dest, {"ffmpeg"},
                              progress, base_pct=0.0, span=60.0)
        _download_and_extract(_FFPROBE_URL_MAC, dest, {"ffprobe"},
                              progress, base_pct=60.0, span=40.0)
    else:
        # Windows / Linux は1つの zip に両方入っている
        _download_and_extract(_FFMPEG_URL_WIN, dest,
                              {FFMPEG_BIN, FFPROBE_BIN}, progress)

    exe = os.path.join(dest, FFMPEG_BIN)
    if not os.path.isfile(exe):
        raise RuntimeError(f"アーカイブ内に {FFMPEG_BIN} が見つかりませんでした。")
    return exe


# ──────────────────────────────────────────────────────
#  Design tokens
# ──────────────────────────────────────────────────────
# Apple Human Interface Guidelines のダークモード・システムカラーに準拠
# https://developer.apple.com/design/human-interface-guidelines/color
P = dict(
    BG="#1c1c1e",        # systemBackground (secondary, elevated)
    CARD="#2c2c2e",      # tertiarySystemBackground
    FIELD="#3a3a3c",     # systemFill
    FIELD_HI="#48484a",  # systemFill hover
    BORDER="#38383a",    # separator
    BORDER_HI="#545456", # separator hover
    ACCENT="#0a84ff",    # systemBlue (dark)
    ACCENT_H="#409cff",  # systemBlue hover
    ACCENT_D="#0069d9",  # systemBlue press
    ACCENT_BG="#0a84ff", # 選択チップ（塗りつぶし）
    FG="#ffffff",        # label
    SUB="#98989f",       # secondaryLabel
    DIM="#6e6e73",       # tertiaryLabel
    SUCCESS="#30d158",   # systemGreen
    WARN="#ffd60a",      # systemYellow
    ERR="#ff453a",       # systemRed
    LOG_BG="#242426",
)

# プラットフォームごとの標準的な UI / 等幅フォント
if _IS_MAC:
    FONT = "Helvetica Neue"   # macOS 標準（SF系が使えない環境でも確実に存在）
    MONO_FONT = "Menlo"
elif _IS_WIN:
    FONT = "Segoe UI"
    MONO_FONT = "Consolas"
else:
    FONT = "DejaVu Sans"
    MONO_FONT = "DejaVu Sans Mono"


def _round_rect(cv: tk.Canvas, x1, y1, x2, y2, r, **kw):
    """smooth polygon による角丸長方形。"""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


# ──────────────────────────────────────────────────────
#  Custom widgets
# ──────────────────────────────────────────────────────
class Tooltip:
    """ウィジェットにマウスオーバーで説明を表示する。"""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _=None):
        if self._tip:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        tk.Label(tw, text=self.text, font=(FONT, 9),
                 bg="#48484a", fg=P["FG"],
                 padx=10, pady=5).pack()

    def _hide(self, _=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None


class RoundedButton(tk.Canvas):
    """Canvas 描画の角丸ボタン。kind: accent / ghost"""

    def __init__(self, master, text, command=None, kind="accent",
                 height=42, radius=12, font=(FONT, 10, "bold"), padx=22):
        super().__init__(master, height=height,
                         bg=master.cget("bg"), highlightthickness=0, bd=0)
        self._text = text
        self._command = command
        self._kind = kind
        self._radius = radius
        self._font = font
        self._state = "normal"
        self._hover = False
        self._press = False
        f = tkfont.Font(font=font)
        self.configure(width=f.measure(text) + padx * 2)
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda _: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _palette(self):
        if self._kind == "accent":
            if self._state == "disabled":
                return "#3a3a3c", "", "#7c7c80"
            fill = P["ACCENT_D"] if self._press else (
                P["ACCENT_H"] if self._hover else P["ACCENT"])
            return fill, "", "#ffffff"
        # ghost
        if self._state == "disabled":
            return P["CARD"], P["BORDER"], "#6e6e73"
        fill = P["FIELD_HI"] if (self._hover or self._press) else P["FIELD"]
        outline = P["BORDER_HI"] if self._hover else P["BORDER"]
        return fill, outline, P["FG"]

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or self.winfo_reqwidth()
        h = self.winfo_height() or self.winfo_reqheight()
        if w < 4 or h < 4:
            return
        fill, outline, fg = self._palette()
        _round_rect(self, 1, 1, w - 2, h - 2, self._radius,
                    fill=fill, outline=outline or fill)
        self.create_text(w / 2, h / 2, text=self._text,
                         font=self._font, fill=fg)

    def _on_enter(self, _):
        self._hover = True
        self._draw()

    def _on_leave(self, _):
        self._hover = False
        self._press = False
        self._draw()

    def _on_press(self, _):
        if self._state == "normal":
            self._press = True
            self._draw()

    def _on_release(self, e):
        was = self._press
        self._press = False
        self._draw()
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if was and inside and self._state == "normal" and self._command:
            self._command()

    def set_state(self, state: str):
        self._state = state
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self._draw()

    def set_text(self, text: str):
        self._text = text
        self._draw()


class ChipGroup(tk.Frame):
    """ピル型の単一選択チップ列。幅が足りないときは自動で折り返す。"""

    def __init__(self, master, values, default, command=None, font=(FONT, 9)):
        super().__init__(master, bg=master.cget("bg"))
        self._value = default
        self._command = command
        self._font = font
        self._order = list(values)
        self._chips: dict[str, tk.Canvas] = {}
        self._last_w = 0
        f = tkfont.Font(font=font)
        for i, v in enumerate(values):
            c = tk.Canvas(self, height=30, width=f.measure(v) + 28,
                          bg=master.cget("bg"), highlightthickness=0,
                          cursor="hand2")
            c.grid(row=0, column=i, padx=(0, 7), pady=(0, 6), sticky="w")
            c.bind("<Button-1>", lambda _, v=v: self.select(v))
            c.bind("<Enter>", lambda _, v=v: self._draw(v, hover=True))
            c.bind("<Leave>", lambda _, v=v: self._draw(v, hover=False))
            self._chips[v] = c
        self.bind("<Configure>", self._reflow)
        self.after(0, self._draw_all)

    def _reflow(self, _=None):
        w = self.winfo_width()
        if w < 60 or w == self._last_w:
            return
        self._last_w = w
        x = row = col = 0
        for v in self._order:
            c = self._chips[v]
            cw = c.winfo_reqwidth() + 7
            if col > 0 and x + cw > w:
                row += 1
                col = 0
                x = 0
            c.grid_configure(row=row, column=col)
            col += 1
            x += cw

    def _draw(self, v, hover=False):
        c = self._chips[v]
        c.delete("all")
        w = c.winfo_reqwidth()
        h = c.winfo_reqheight()
        if v == self._value:
            fill, outline, fg = P["ACCENT_BG"], P["ACCENT"], P["FG"]
        else:
            fill = P["FIELD_HI"] if hover else P["FIELD"]
            outline = P["BORDER_HI"] if hover else P["BORDER"]
            fg = P["SUB"]
        _round_rect(c, 1, 1, w - 2, h - 2, (h - 2) / 2, fill=fill, outline=outline)
        c.create_text(w / 2, h / 2, text=v, font=self._font, fill=fg)

    def _draw_all(self):
        for v in self._chips:
            self._draw(v)

    def select(self, v):
        self._value = v
        self._draw_all()
        if self._command:
            self._command(v)

    def get(self):
        return self._value


class Switch(tk.Frame):
    """トグルスイッチ + ラベル。"""

    def __init__(self, master, text, value=False, command=None):
        super().__init__(master, bg=master.cget("bg"))
        self._value = value
        self._command = command
        self._cv = tk.Canvas(self, width=42, height=24,
                             bg=master.cget("bg"), highlightthickness=0,
                             cursor="hand2")
        self._cv.pack(side="left")
        self._label = tk.Label(self, text=text, font=(FONT, 9),
                               bg=master.cget("bg"), fg=P["SUB"],
                               cursor="hand2")
        self._label.pack(side="left", padx=(8, 0))
        for w in (self._cv, self._label):
            w.bind("<Button-1>", lambda _: self.toggle())
        self._draw()

    def _draw(self):
        c = self._cv
        c.delete("all")
        w, h = 42, 24
        # macOS/iOS のトグルは ON=systemGreen
        track = P["SUCCESS"] if self._value else "#39393b"
        _round_rect(c, 1, 3, w - 1, h - 3, (h - 6) / 2, fill=track, outline=track)
        kx = w - 11 if self._value else 11
        c.create_oval(kx - 7, h / 2 - 7, kx + 7, h / 2 + 7,
                      fill="#ffffff", outline="#ffffff")
        self._label.configure(fg=P["FG"] if self._value else P["SUB"])

    def toggle(self):
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)

    def get(self):
        return self._value


class RoundedField(tk.Canvas):
    """角丸の入力欄コンテナ。inner フレームに Entry 等を配置する。"""

    def __init__(self, master, height=48, radius=12):
        # width は小さめに要求し、pack の割り当てに従って伸縮させる
        super().__init__(master, height=height, width=60,
                         bg=master.cget("bg"), highlightthickness=0, bd=0)
        self._radius = radius
        self._focus = False
        self.inner = tk.Frame(self, bg=P["FIELD"])
        self.bind("<Configure>", lambda _: self._draw())

    def set_focus_style(self, flag: bool):
        self._focus = flag
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        outline = P["ACCENT"] if self._focus else P["BORDER"]
        _round_rect(self, 1, 1, w - 2, h - 2, self._radius,
                    fill=P["FIELD"], outline=outline)
        self.create_window(14, h / 2, window=self.inner,
                           anchor="w", width=w - 28, height=h - 16)


class RoundedProgress(tk.Canvas):
    """角丸のプログレスバー。"""

    def __init__(self, master, height=8):
        super().__init__(master, height=height,
                         bg=master.cget("bg"), highlightthickness=0, bd=0)
        self._pct = 0.0
        self._color = P["ACCENT"]
        self.bind("<Configure>", lambda _: self._draw())

    def set(self, pct: float, color: str | None = None):
        self._pct = max(0.0, min(100.0, pct))
        if color:
            self._color = color
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 4:
            return
        # Tk は 8桁(アルファ付き)カラー非対応。トラックは不透明色のみで描く
        _round_rect(self, 0, 0, w - 1, h - 1, h / 2,
                    fill="#3a3a3c", outline="#3a3a3c")
        fw = w * self._pct / 100
        if fw >= h:
            _round_rect(self, 0, 0, fw - 1, h - 1, h / 2,
                        fill=self._color, outline=self._color)


class Card(tk.Canvas):
    """角丸カード。self.inner に内容を配置する。expand=True で親に合わせて伸縮。"""

    def __init__(self, master, padx=20, pady=16, radius=12, expand=False):
        super().__init__(master, bg=master.cget("bg"),
                         highlightthickness=0, bd=0)
        self._padx, self._pady = padx, pady
        self._radius = radius
        self._expand = expand
        self.inner = tk.Frame(self, bg=P["CARD"])
        self.bind("<Configure>", lambda _: self._draw())
        if not expand:
            self.inner.bind("<Configure>", lambda _: self._fit())
            # Tk 9.0 では inner の <Configure> が中身の増減で発火しないことがあり、
            # カードの高さが更新されずに内容がクリップされる。初期表示を確実にする
            # ため、レイアウト確定後に明示的な再フィットを予約する。
            self.after_idle(self.refit)

    def _fit(self):
        h = self.inner.winfo_reqheight() + 2 * self._pady
        if self.winfo_height() != h:
            self.configure(height=h)

    def refit(self):
        """内容の高さに合わせてカードを確実に再計算・再描画する。
        設定の開閉など、中身のサイズが変わったときに呼ぶ。"""
        if self._expand:
            self._draw()
            return
        try:
            self.inner.update_idletasks()
        except tk.TclError:
            return
        h = self.inner.winfo_reqheight() + 2 * self._pady
        self.configure(height=h)
        self.update_idletasks()
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        _round_rect(self, 0, 0, w - 1, h - 1, self._radius,
                    fill=P["CARD"], outline=P["BORDER"])
        ih = (h - 2 * self._pady) if self._expand \
            else self.inner.winfo_reqheight()
        self.create_window(self._padx, self._pady, window=self.inner,
                           anchor="nw", width=w - 2 * self._padx, height=ih)


class Pill(tk.Canvas):
    """ステータスドット付きのピルバッジ。"""

    def __init__(self, master, text="", dot=P["SUB"], font=(FONT, 9)):
        super().__init__(master, height=28, bg=master.cget("bg"),
                         highlightthickness=0, bd=0)
        self._font = font
        self.set(text, dot)

    def set(self, text: str, dot: str):
        self._text, self._dot = text, dot
        f = tkfont.Font(font=self._font)
        self.configure(width=f.measure(text) + 44)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        _round_rect(self, 1, 1, w - 2, h - 2, (h - 2) / 2,
                    fill=P["FIELD"], outline=P["BORDER"])
        self.create_oval(14, h / 2 - 4, 22, h / 2 + 4,
                         fill=self._dot, outline=self._dot)
        self.create_text(30, h / 2, text=self._text, anchor="w",
                         font=self._font, fill=P["SUB"])


class LinkLabel(tk.Label):
    """ホバーで明るくなるリンク風ラベル。"""

    def __init__(self, master, text, command=None, font=(FONT, 9)):
        super().__init__(master, text=text, font=font,
                         bg=master.cget("bg"), fg=P["SUB"], cursor="hand2")
        self._command = command
        self.bind("<Enter>", lambda _: self.configure(fg=P["FG"]))
        self.bind("<Leave>", lambda _: self.configure(fg=P["SUB"]))
        self.bind("<Button-1>", lambda _: command and command())


# ──────────────────────────────────────────────────────
#  App icon (64x64 PNG, base64 embedded — make_icon.py で生成)
# ──────────────────────────────────────────────────────
_ICON_B64 = (
    "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"
)


class _YdlLogger:
    """yt-dlp の実行ログを GUI のログ欄へ流す。"""

    def __init__(self, app):
        self._app = app

    def _post(self, msg, tag):
        self._app.after(0, self._app._log_msg, msg, tag)

    def debug(self, msg):
        # [youtube] Extracting URL / [download] Destination / [Merger] ... など
        # 進行段階が分かる行だけ表示する
        if msg.startswith("[") and not msg.startswith("[debug]"):
            self._post(msg, "dim")

    def info(self, msg):
        self._post(msg, "info")

    def warning(self, msg):
        self._post(f"警告: {msg}", "warn")

    def error(self, msg):
        self._post(msg, "error")


# ──────────────────────────────────────────────────────
#  Main application
# ──────────────────────────────────────────────────────
_URL_PLACEHOLDER = "動画のURLを貼り付け（Enterで開始）"

_FORMATS = ["MP4（推奨）", "最高画質", "MP3", "M4A"]
_QUALITIES = ["制限なし", "4K", "2K", "1080p", "720p", "480p"]
_Q_HEIGHTS = {"4K": 2160, "2K": 1440, "1080p": 1080, "720p": 720, "480p": 480}


class VideoDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        _load_config()
        self.title("Video Downloader")
        self.configure(bg=P["BG"])
        self.minsize(520, 460)
        self._set_app_icon()
        self._center_window(900, 720)
        self._build_ui()
        self.update_idletasks()
        self._enable_dark_titlebar()
        self._bring_to_front()
        self._check_ytdlp()
        self.bind("<FocusIn>", self._auto_paste, add="+")
        self.bind("<Configure>", self._on_window_resize, add="+")

    def _bring_to_front(self):
        """ターミナル（.command のダブルクリック）から起動したとき、
        ウィンドウが他アプリの背後に隠れないよう最前面へ持ってくる。
        アクセシビリティ権限は不要。一瞬だけ最前面固定してすぐ解除する。"""
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(700, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def report_callback_exception(self, exc, val, tb):
        """GUI コールバック内の例外を stderr ではなくログに出す
        （windowed exe では stderr が見えず「無反応」になるため）。"""
        detail = "".join(traceback.format_exception(exc, val, tb))
        print(detail, file=sys.stderr)
        try:
            self._log_msg(f"内部エラー: {val}", "error")
        except Exception:
            pass

    # ── Window chrome ──────────────────────────────────
    def _set_app_icon(self):
        # exe のファイルアイコンは PyInstaller (icon.ico) が埋め込む。
        # ウィンドウ・タスクバーのアイコンはここで設定する。
        try:
            self._icon_img = tk.PhotoImage(data=_ICON_B64)
            self.iconphoto(True, self._icon_img)
        except tk.TclError:
            self._icon_img = None

    def _center_window(self, w: int, h: int):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2 - 20, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _enable_dark_titlebar(self):
        """Windows のタイトルバーをダークモードにする。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20; 19 on old builds)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value),
                        ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    # ── UI construction ────────────────────────────────
    def _build_ui(self):
        root = tk.Frame(self, bg=P["BG"])
        root.pack(fill="both", expand=True, padx=24, pady=(18, 16))

        # ─ Header ─
        hdr = tk.Frame(root, bg=P["BG"])
        hdr.pack(fill="x", pady=(0, 20))
        if getattr(self, "_icon_img", None):
            self._icon_small = self._icon_img.subsample(2, 2)  # 32x32
            tk.Label(hdr, image=self._icon_small, bg=P["BG"]).pack(
                side="left", padx=(0, 12))
        tbox = tk.Frame(hdr, bg=P["BG"])
        tbox.pack(side="left")
        tk.Label(tbox, text="Video Downloader",
                 font=(FONT, 17, "bold"), bg=P["BG"], fg=P["FG"]).pack(anchor="w")
        tk.Label(tbox, text=f"URLを貼り付けるだけで動画・音声を保存  ·  v{APP_VERSION}",
                 font=(FONT, 9), bg=P["BG"], fg=P["DIM"]).pack(anchor="w")
        self._ytdlp_badge = Pill(hdr, "yt-dlp 確認中…", P["WARN"])
        self._ytdlp_badge.pack(side="right")
        self._update_btn = RoundedButton(hdr, "🔄", kind="ghost",
                                         height=28, radius=14,
                                         font=(FONT, 10), padx=10,
                                         command=self._update_ytdlp)
        self._update_btn.pack(side="right", padx=(0, 8))
        Tooltip(self._update_btn, "yt-dlp を最新版に更新")

        # ─ URL ─
        self._url_field = RoundedField(root, height=52)
        self._url_field.pack(fill="x", pady=(0, 14))
        fi = self._url_field.inner
        self._url_var = tk.StringVar()
        self._url_entry = tk.Entry(fi, textvariable=self._url_var,
                                   font=(FONT, 12), bg=P["FIELD"],
                                   fg=P["FG"], insertbackground=P["ACCENT"],
                                   relief="flat", bd=0)
        self._url_entry.pack(side="left", fill="both", expand=True)
        self._url_entry.bind("<Return>", lambda _: self._start_download())
        self._url_entry.bind("<FocusIn>", self._on_url_focus_in)
        self._url_entry.bind("<FocusOut>", self._on_url_focus_out)
        clear = LinkLabel(fi, "✕", command=self._clear_url, font=(FONT, 11))
        clear.configure(bg=P["FIELD"])
        clear.pack(side="right", padx=(10, 0))
        Tooltip(clear, "URL欄を空にする")
        paste = LinkLabel(fi, "📋 貼り付け", command=self._paste_url)
        paste.configure(bg=P["FIELD"], fg=P["ACCENT"])
        paste.bind("<Leave>", lambda _: paste.configure(fg=P["ACCENT"]))
        paste.pack(side="right", padx=(12, 0))
        Tooltip(paste, "クリップボードのURLを貼り付け")
        self._placeholder_on = False
        self._show_placeholder()

        # ─ Options card (折りたたみ可能) ─
        oc = Card(root)
        oc.pack(fill="x", pady=(0, 14))
        self._opt_card = oc
        inner = oc.inner

        ohdr = tk.Frame(inner, bg=P["CARD"])
        ohdr.pack(fill="x")
        tk.Label(ohdr, text="設定", font=(FONT, 10, "bold"),
                 bg=P["CARD"], fg=P["FG"]).pack(side="left")
        self._opt_toggle = LinkLabel(ohdr, "▲ たたむ",
                                     command=self._toggle_options)
        self._opt_toggle.pack(side="right")
        Tooltip(self._opt_toggle, "設定をたたんでウィンドウを小さくできます")

        self._opts_collapsed = False
        self._opt_body = tk.Frame(inner, bg=P["CARD"])
        self._opt_body.pack(fill="x", pady=(12, 0))
        body = self._opt_body

        tk.Label(body, text="フォーマット", font=(FONT, 9),
                 bg=P["CARD"], fg=P["DIM"]).pack(anchor="w", pady=(0, 6))
        self._format_chips = ChipGroup(body, _FORMATS, "MP4（推奨）")
        self._format_chips.pack(fill="x")

        tk.Label(body, text="最大解像度", font=(FONT, 9),
                 bg=P["CARD"], fg=P["DIM"]).pack(anchor="w", pady=(8, 6))
        self._quality_chips = ChipGroup(body, _QUALITIES, "制限なし")
        self._quality_chips.pack(fill="x")

        tk.Label(body, text="保存先", font=(FONT, 9),
                 bg=P["CARD"], fg=P["DIM"]).pack(anchor="w", pady=(10, 6))
        fr = tk.Frame(body, bg=P["CARD"])
        fr.pack(fill="x")
        self._folder_field = RoundedField(fr, height=40)
        self._folder_field.pack(side="left", fill="x", expand=True)
        _default_media = "Movies" if _IS_MAC else "Videos"
        default_dir = _config.get(OUTPUT_DIR_KEY,
                                  os.path.join(os.path.expanduser("~"), _default_media))
        self._output_var = tk.StringVar(value=default_dir)
        out_entry = tk.Entry(self._folder_field.inner,
                             textvariable=self._output_var,
                             font=(FONT, 10), bg=P["FIELD"], fg=P["FG"],
                             insertbackground=P["ACCENT"], relief="flat", bd=0)
        out_entry.pack(fill="both", expand=True)
        out_entry.bind("<FocusIn>",
                       lambda _: self._folder_field.set_focus_style(True))
        out_entry.bind("<FocusOut>",
                       lambda _: self._folder_field.set_focus_style(False))
        browse = RoundedButton(fr, "📂 参照", kind="ghost", height=40,
                               font=(FONT, 9), padx=14,
                               command=self._browse_folder)
        browse.pack(side="left", padx=(8, 0))
        Tooltip(browse, "保存先フォルダを選択")
        openf = RoundedButton(fr, "開く", kind="ghost", height=40,
                              font=(FONT, 9), padx=14,
                              command=self._open_output_folder)
        openf.pack(side="left", padx=(6, 0))
        Tooltip(openf, "保存先フォルダを Finder で開く" if _IS_MAC
                else "保存先フォルダをエクスプローラーで開く")

        self._open_after = Switch(
            body, "ダウンロード完了後にフォルダを開く",
            value=_config.get(OPEN_AFTER_KEY, "0") == "1",
            command=self._save_open_after)
        self._open_after.pack(anchor="w", pady=(14, 0))
        if _config.get(OPTS_COLLAPSED_KEY, "0") == "1":
            self._toggle_options(save=False)

        # ─ Action row ─
        ar = tk.Frame(root, bg=P["BG"])
        ar.pack(fill="x", pady=(0, 14))
        self._dl_btn = RoundedButton(ar, "↓  ダウンロード開始",
                                     kind="accent", height=48, radius=14,
                                     font=(FONT, 12, "bold"),
                                     command=self._start_download)
        self._dl_btn.pack(side="left", fill="x", expand=True)
        self._cancel_btn = RoundedButton(ar, "キャンセル", kind="ghost",
                                         height=48, radius=14,
                                         font=(FONT, 10),
                                         command=self._cancel_download)
        self._cancel_btn.pack(side="left", padx=(10, 0))
        self._cancel_btn.set_state("disabled")

        # ─ Status / log card ─
        st = Card(root, expand=True, pady=14)
        st.pack(fill="both", expand=True)
        si = st.inner

        srow = tk.Frame(si, bg=P["CARD"])
        srow.pack(fill="x")
        self._status_label = tk.Label(srow, text="待機中", font=(FONT, 10),
                                      bg=P["CARD"], fg=P["SUB"], anchor="w")
        self._status_label.pack(side="left", fill="x", expand=True)
        self._meta_label = tk.Label(srow, text="", font=(FONT, 9),
                                    bg=P["CARD"], fg=P["DIM"])
        self._meta_label.pack(side="right")

        self._progress = RoundedProgress(si, height=6)
        self._progress.pack(fill="x", pady=(8, 12))

        lrow = tk.Frame(si, bg=P["CARD"])
        lrow.pack(fill="x")
        tk.Label(lrow, text="ログ", font=(FONT, 9),
                 bg=P["CARD"], fg=P["DIM"]).pack(side="left")
        LinkLabel(lrow, "クリア", command=self._clear_log).pack(side="right")

        tf = tk.Frame(si, bg=P["LOG_BG"])
        tf.pack(fill="both", expand=True, pady=(6, 0))
        self._log = tk.Text(tf, font=(MONO_FONT, 11 if _IS_MAC else 9),
                            bg=P["LOG_BG"], fg=P["FG"], relief="flat", bd=0,
                            wrap="word", state="disabled",
                            padx=10, pady=8, height=3)
        self._log_sb = tk.Scrollbar(tf, command=self._log.yview,
                                    orient="vertical", width=10)
        self._log.configure(yscrollcommand=self._on_log_scroll)
        self._log.pack(side="left", fill="both", expand=True)
        self._log.tag_config("info",    foreground=P["FG"])
        self._log.tag_config("success", foreground=P["SUCCESS"])
        self._log.tag_config("warn",    foreground=P["WARN"])
        self._log.tag_config("error",   foreground=P["ERR"])
        self._log.tag_config("dim",     foreground=P["SUB"])

        self._downloading = False
        self._cancel_flag = False
        self._ydl_ref = None
        self._ffmpeg_path = None
        self._ffmpeg_downloading = False

    # ── Options collapse ───────────────────────────────
    def _on_window_resize(self, event):
        """ウィンドウが低くなったら設定を自動でたたむ（自動では開かない）。"""
        if event.widget is self and event.height < 660 and not self._opts_collapsed:
            self._toggle_options(save=False)

    def _toggle_options(self, save=True):
        self._opts_collapsed = not self._opts_collapsed
        if self._opts_collapsed:
            self._opt_body.pack_forget()
            self._opt_toggle.configure(text="▼ ひらく")
        else:
            self._opt_body.pack(fill="x", pady=(12, 0))
            self._opt_toggle.configure(text="▲ たたむ")
        # Tk 9.0 では pack/forget だけではカードの高さが追従せず内容が
        # クリップされる（＝ボタンが押せない）ため、明示的に再フィットする。
        if getattr(self, "_opt_card", None):
            self.after_idle(self._opt_card.refit)
        if save:
            _config[OPTS_COLLAPSED_KEY] = "1" if self._opts_collapsed else "0"
            _save_config()

    # ── URL placeholder ────────────────────────────────
    def _show_placeholder(self):
        if not self._url_var.get():
            self._placeholder_on = True
            self._url_entry.configure(fg=P["DIM"])
            self._url_var.set(_URL_PLACEHOLDER)

    def _hide_placeholder(self):
        if self._placeholder_on:
            self._placeholder_on = False
            self._url_var.set("")
            self._url_entry.configure(fg=P["FG"])

    def _on_url_focus_in(self, _=None):
        self._url_field.set_focus_style(True)
        self._hide_placeholder()

    def _on_url_focus_out(self, _=None):
        self._url_field.set_focus_style(False)
        self._show_placeholder()

    def _get_url(self) -> str:
        return "" if self._placeholder_on else self._url_var.get().strip()

    def _set_url(self, url: str):
        self._hide_placeholder()
        self._placeholder_on = False
        self._url_entry.configure(fg=P["FG"])
        self._url_var.set(url)

    def _clear_url(self):
        self._url_var.set("")
        if self.focus_get() is not self._url_entry:
            self._show_placeholder()

    def _auto_paste(self, event):
        """ウィンドウにフォーカスが戻ったとき、クリップボードのURLを自動入力。"""
        if event.widget is not self or self._downloading:
            return
        if self._get_url():
            return
        try:
            clip = self.clipboard_get().strip()
        except tk.TclError:
            return
        if clip.startswith(("http://", "https://")) and "\n" not in clip:
            self._set_url(clip)
            self._log_msg("クリップボードからURLを自動入力しました。", "dim")

    # ── yt-dlp check ───────────────────────────────────
    def _check_ytdlp(self):
        if yt_dlp is None:
            self._ytdlp_badge.set("yt-dlp 未インストール", P["ERR"])
            self._log_msg("yt-dlp が見つかりません。右上の 🔄 ボタンでインストールしてください。",
                          "error")
            return
        ver = getattr(yt_dlp.version, "__version__", "不明")
        src = "libs/" if _YTDLP_SOURCE == "libs" else "内蔵"
        self._ytdlp_badge.set(f"yt-dlp {ver}", P["SUCCESS"])
        self._log_msg(f"yt-dlp {ver} を検出しました ({src})。", "dim")
        self._ffmpeg_path = _find_ffmpeg()
        if self._ffmpeg_path:
            self._log_msg(f"ffmpeg を検出しました: {self._ffmpeg_path}", "dim")
        else:
            self._log_msg("ffmpeg が見つからないため、自動セットアップを開始します"
                          "（初回のみ）。", "warn")
            self._ffmpeg_downloading = True
            threading.Thread(target=self._ffmpeg_setup_thread,
                             daemon=True).start()
        threading.Thread(target=self._check_ytdlp_update, daemon=True).start()

    def _ffmpeg_setup_thread(self):
        last = -25

        def progress(pct):
            nonlocal last
            if pct - last >= 25:
                last = pct
                self.after(0, self._log_msg,
                           f"ffmpeg をダウンロード中… {pct:.0f}%", "dim")

        try:
            path = _download_ffmpeg(progress)
            self._ffmpeg_path = path
            self.after(0, self._log_msg,
                       "ffmpeg のセットアップが完了しました。", "success")
        except Exception as e:
            self.after(0, self._log_msg,
                       f"ffmpeg の自動セットアップに失敗しました: {e}", "error")
            hint = ("Homebrew で `brew install ffmpeg` を実行すると使えます。"
                    if _IS_MAC else
                    f"手動で {FFMPEG_BIN} をアプリと同じフォルダに置いても使えます。")
            self.after(0, self._log_msg, hint, "warn")
        finally:
            self._ffmpeg_downloading = False

    def _check_ytdlp_update(self):
        """起動時にバックグラウンドで yt-dlp の新バージョンを確認する。"""
        try:
            latest = _fetch_json(_PYPI_URL)["info"]["version"]
            current = getattr(yt_dlp.version, "__version__", None)
            if current and not _same_version(current, latest):
                self.after(0, self._ytdlp_badge.set,
                           f"yt-dlp {current} → {latest} 更新あり", P["WARN"])
                self.after(0, self._log_msg,
                           f"yt-dlp の新バージョン {latest} があります。"
                           "右上の 🔄 ボタンで更新してください。", "warn")
        except Exception:
            pass  # オフライン時などは黙って無視

    # ── Helpers ────────────────────────────────────────
    def _on_log_scroll(self, first, last):
        """ログが溢れたときだけスクロールバーを表示する。"""
        if float(first) <= 0.0 and float(last) >= 1.0:
            self._log_sb.pack_forget()
        elif not self._log_sb.winfo_ismapped():
            self._log_sb.pack(side="right", fill="y")
        self._log_sb.set(first, last)

    def _log_msg(self, text, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] {text}\n", tag)
        self._log.configure(state="disabled")
        self._log.see("end")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _save_open_after(self, value: bool):
        _config[OPEN_AFTER_KEY] = "1" if value else "0"
        _save_config()

    def _paste_url(self):
        try:
            self._set_url(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self._output_var.get())
        if folder:
            self._output_var.set(folder)
            _config[OUTPUT_DIR_KEY] = folder
            _save_config()

    def _open_output_folder(self):
        folder = self._output_var.get()
        if os.path.isdir(folder):
            _open_in_file_manager(folder)
        else:
            messagebox.showwarning("フォルダが見つかりません",
                                   f"フォルダが存在しません:\n{folder}")

    def _set_downloading(self, state: bool):
        self._downloading = state
        self._dl_btn.set_state("disabled" if state else "normal")
        self._dl_btn.set_text("ダウンロード中…" if state else "↓  ダウンロード開始")
        self._cancel_btn.set_state("normal" if state else "disabled")

    def _set_status(self, text: str, color: str | None = None, meta: str = ""):
        self._status_label.configure(text=text, fg=color or P["SUB"])
        self._meta_label.configure(text=meta)

    # ── Format string ──────────────────────────────────
    def _build_format_string(self):
        fmt = self._format_chips.get()
        hlim = _Q_HEIGHTS.get(self._quality_chips.get())

        if fmt == "MP3":
            return "bestaudio/best", {"postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]}
        if fmt == "M4A":
            return "bestaudio[ext=m4a]/bestaudio/best", {}
        if fmt == "最高画質":
            f = (f"bestvideo[height<={hlim}]+bestaudio/best[height<={hlim}]/best"
                 if hlim else "bestvideo+bestaudio/best")
            return f, {}

        # MP4 / H.264 (default)
        if hlim:
            f = (f"bestvideo[ext=mp4][vcodec^=avc][height<={hlim}]+bestaudio[ext=m4a]"
                 f"/bestvideo[ext=mp4][vcodec^=avc][height<={hlim}]+bestaudio"
                 f"/best[ext=mp4][height<={hlim}]/best[height<={hlim}]/best")
        else:
            f = ("bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]"
                 "/bestvideo[ext=mp4][vcodec^=avc]+bestaudio/best[ext=mp4]/best")
        return f, {}

    # ── Download ───────────────────────────────────────
    def _start_download(self):
        if yt_dlp is None:
            messagebox.showerror("エラー",
                                 "yt-dlp が見つかりません。\n右上の 🔄 ボタンでインストールしてください。")
            return
        url = self._get_url()
        if not url:
            messagebox.showwarning("URLが必要です", "ダウンロードするURLを入力してください。")
            return
        out = self._output_var.get().strip()
        if not out:
            messagebox.showwarning("保存先が必要です", "保存先フォルダを選択してください。")
            return
        # M4A 以外は結合・変換に ffmpeg が必要
        if self._format_chips.get() != "M4A" and not self._ffmpeg_path:
            if self._ffmpeg_downloading:
                messagebox.showinfo(
                    "ffmpeg を準備中です",
                    "ffmpeg の自動セットアップが完了してからお試しください。\n"
                    "進行状況はログに表示されます。")
                return
            self._log_msg("ffmpeg なしで続行します。高画質の結合や MP3 変換は"
                          "失敗する可能性があります。", "warn")
        os.makedirs(out, exist_ok=True)
        self._cancel_flag = False
        self._set_downloading(True)
        self._progress.set(0, P["ACCENT"])
        self._set_status("準備中…")
        self._log_msg(f"開始: {url}", "dim")
        threading.Thread(target=self._download_thread,
                         args=(url, out), daemon=True).start()

    def _cancel_download(self):
        self._cancel_flag = True
        self._log_msg("キャンセルを要求しました…", "warn")

    def _download_thread(self, url, out):
        def hook(d):
            if self._cancel_flag:
                raise yt_dlp.utils.DownloadCancelled()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                dl = d.get("downloaded_bytes", 0)
                pct = dl / total * 100 if total else 0
                speed = d.get("speed")
                eta = d.get("eta")
                parts = [f"{pct:.1f}%"]
                if total:
                    parts.append(f"{_fmt_size(dl)} / {_fmt_size(total)}")
                if speed:
                    parts.append(_fmt_speed(speed))
                if eta:
                    parts.append(f"残り {_fmt_time(eta)}")
                fn = os.path.basename(d.get("filename", ""))
                self.after(0, self._update_progress,
                           pct, fn or "ダウンロード中…", "  ·  ".join(parts))
            elif d.get("status") == "finished":
                self.after(0, self._update_progress, 100,
                           "ダウンロード完了・後処理待ち…", "")

        def pp_hook(d):
            if d.get("status") == "started":
                pp = d.get("postprocessor", "")
                label = {"Merger": "映像と音声を結合中…",
                         "FFmpegExtractAudio": "音声を変換中…",
                         "MoveFiles": "ファイルを移動中…"}.get(pp)
                if label:
                    self.after(0, self._set_status, label, P["FG"], "")

        try:
            fmt_str, extra = self._build_format_string()
            opts = {
                "format": fmt_str,
                "outtmpl": os.path.join(out, "%(title)s.%(ext)s"),
                "merge_output_format": "mp4",
                "noplaylist": True,
                "progress_hooks": [hook],
                "postprocessor_hooks": [pp_hook],
                "logger": _YdlLogger(self),
                "noprogress": True,
                "quiet": True,
            }
            if self._ffmpeg_path:
                opts["ffmpeg_location"] = os.path.dirname(self._ffmpeg_path)
            opts.update(extra)
            self.after(0, self._set_status, "動画情報を取得中…", P["FG"], "")
            with yt_dlp.YoutubeDL(opts) as ydl:
                self._ydl_ref = ydl
                info = ydl.extract_info(url, download=True)
                self._ydl_ref = None
            title = info.get("title", "（タイトル不明）")
            res = info.get("resolution") or (
                f"{info.get('width')}x{info.get('height')}" if info.get("width") else "不明")
            vcodec = info.get("vcodec", "不明")
            filename = ydl.prepare_filename(info)
            self.after(0, self._on_success, title, res, vcodec, filename)
        except yt_dlp.utils.DownloadCancelled:
            self.after(0, self._on_cancelled)
        except yt_dlp.utils.DownloadError as e:
            self.after(0, self._on_error, str(e))
        except Exception:
            self.after(0, self._on_error, traceback.format_exc())

    def _update_progress(self, pct, status, meta):
        self._progress.set(pct, P["ACCENT"])
        self._set_status(status, P["FG"], meta)

    def _on_success(self, title, res, vcodec, filename):
        self._set_downloading(False)
        self._progress.set(100, P["SUCCESS"])
        self._set_status("✔ 完了", P["SUCCESS"])
        self._log_msg(f"完了: {title}", "success")
        self._log_msg(f"  解像度: {res}  コーデック: {vcodec}", "dim")
        self._log_msg(f"  保存先: {filename}", "dim")
        if self._open_after.get():
            self._open_output_folder()

    def _on_cancelled(self):
        self._set_downloading(False)
        self._progress.set(0)
        self._set_status("キャンセルされました", P["WARN"])
        self._log_msg("ダウンロードをキャンセルしました。", "warn")

    def _on_error(self, msg):
        self._set_downloading(False)
        self._progress.set(0)
        self._set_status("✖ エラー", P["ERR"])
        self._log_msg(f"エラー: {msg.splitlines()[-1] if msg else '不明'}", "error")
        self._log_msg("URLが正しいか、動画が公開されているか確認してください。", "warn")

    # ── yt-dlp updater ─────────────────────────────────
    def _update_ytdlp(self):
        self._update_btn.set_state("disabled")
        self._log_msg("PyPI から yt-dlp の最新バージョンを確認中…", "dim")
        threading.Thread(target=self._update_thread, daemon=True).start()

    def _update_thread(self):
        try:
            old_ver, new_ver = _download_latest_ytdlp(_LIBS_DIR)
            if old_ver is None:
                self.after(0, self._log_msg,
                           f"yt-dlp はすでに最新バージョンです ({new_ver})。", "info")
            else:
                self.after(0, self._log_msg,
                           f"yt-dlp を {old_ver or '内蔵版'} → {new_ver} に更新しました。", "success")
                self.after(0, self._log_msg,
                           "アプリを再起動すると新バージョンが有効になります。", "warn")
        except Exception as e:
            self.after(0, self._log_msg, f"更新に失敗しました: {e}", "error")
        finally:
            self.after(0, self._update_btn.set_state, "normal")


# ──────────────────────────────────────────────────────
#  Utilities
# ──────────────────────────────────────────────────────
def _fmt_size(b: float) -> str:
    if b >= 1_000_000_000:
        return f"{b/1_000_000_000:.2f} GB"
    if b >= 1_000_000:
        return f"{b/1_000_000:.1f} MB"
    return f"{b/1_000:.0f} KB"


def _fmt_speed(bps: float) -> str:
    if bps >= 1_000_000:
        return f"{bps/1_000_000:.1f} MB/s"
    if bps >= 1_000:
        return f"{bps/1_000:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _open_in_file_manager(path: str):
    """保存先フォルダを OS 標準のファイルマネージャで開く。
    Windows=エクスプローラー / macOS=Finder / Linux=xdg-open"""
    try:
        if _IS_WIN:
            os.startfile(path)          # type: ignore[attr-defined]
        elif _IS_MAC:
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception:
        pass


def _fmt_time(s: int) -> str:
    if s >= 3600:
        return f"{s//3600}時間{s%3600//60}分"
    if s >= 60:
        return f"{s//60}分{s%60}秒"
    return f"{s}秒"


# ──────────────────────────────────────────────────────
if __name__ == "__main__":
    app = VideoDownloaderApp()
    app.mainloop()
