import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os
import re
import io
import json
import shutil
import zipfile
import urllib.request
from datetime import datetime


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

try:
    import yt_dlp
    _YTDLP_SOURCE = "libs" if os.path.isdir(os.path.join(_LIBS_DIR, "yt_dlp")) else "bundled"
except ImportError:
    yt_dlp = None
    _YTDLP_SOURCE = "none"


# ──────────────────────────────────────────────────────
#  Config persistence
# ──────────────────────────────────────────────────────
OUTPUT_DIR_KEY = "output_dir"
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
_UA = "VideoDownloader/2.0 (yt-dlp-updater)"


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
    if current == latest:
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
#  Main application
# ──────────────────────────────────────────────────────
class VideoDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        _load_config()
        self.title("Video Downloader")
        self.geometry("780x600")
        self.minsize(640, 480)
        self.configure(bg="#1e1e2e")
        self._build_ui()
        self._check_ytdlp()

    # ── UI construction ────────────────────────────────
    def _build_ui(self):
        BG = "#1e1e2e"; CARD = "#2a2a3e"; ACC = "#7c3aed"; ACC2 = "#6d28d9"
        FG = "#e2e8f0"; SUB = "#94a3b8"
        SUCCESS = "#22c55e"; WARN = "#f59e0b"; ERR = "#ef4444"
        self._colors = dict(BG=BG, CARD=CARD, FG=FG, SUB=SUB,
                            SUCCESS=SUCCESS, WARN=WARN, ERR=ERR)

        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",        background=BG)
        s.configure("Card.TFrame",   background=CARD)
        s.configure("TLabel",        background=BG,   foreground=FG)
        s.configure("Card.TLabel",   background=CARD, foreground=FG)
        s.configure("CardSub.TLabel",background=CARD, foreground=SUB, font=("Segoe UI", 9))
        s.configure("Accent.TButton",
                    background=ACC, foreground="white",
                    font=("Segoe UI", 10, "bold"),
                    borderwidth=0, focusthickness=0, padding=(16, 8))
        s.map("Accent.TButton",
              background=[("active", ACC2), ("disabled", "#4b4b6e")],
              foreground=[("disabled", "#888")])
        s.configure("TButton",
                    background=CARD, foreground=FG,
                    font=("Segoe UI", 9),
                    borderwidth=0, focusthickness=0, padding=(10, 6))
        s.map("TButton",
              background=[("active", "#3a3a5e"), ("disabled", "#252535")],
              foreground=[("disabled", "#666")])
        s.configure("TEntry",
                    fieldbackground=CARD, foreground=FG,
                    insertcolor=FG, borderwidth=1, relief="flat")
        s.configure("Horizontal.TProgressbar",
                    troughcolor=CARD, background=ACC, thickness=6, borderwidth=0)
        s.configure("TCombobox",
                    fieldbackground=CARD, background=CARD,
                    foreground=FG, arrowcolor=SUB, borderwidth=0)
        s.map("TCombobox",
              fieldbackground=[("readonly", CARD)],
              foreground=[("readonly", FG)])

        root = ttk.Frame(self, style="TFrame", padding=20)
        root.pack(fill="both", expand=True)

        # Header
        hdr = ttk.Frame(root, style="TFrame")
        hdr.pack(fill="x", pady=(0, 16))
        tk.Label(hdr, text="Video Downloader",
                 font=("Segoe UI", 18, "bold"), bg=BG, fg=FG).pack(side="left")
        self._ytdlp_badge = tk.Label(hdr, text="yt-dlp 確認中…",
                                     font=("Segoe UI", 9), bg=BG, fg=SUB)
        self._ytdlp_badge.pack(side="right", padx=(0, 4))

        # URL card
        uc = ttk.Frame(root, style="Card.TFrame", padding=14)
        uc.pack(fill="x", pady=(0, 10))
        ttk.Label(uc, text="URL", style="CardSub.TLabel").pack(anchor="w")
        ur = ttk.Frame(uc, style="Card.TFrame")
        ur.pack(fill="x", pady=(4, 0))
        self._url_var = tk.StringVar()
        self._url_entry = tk.Entry(ur, textvariable=self._url_var,
                                   font=("Segoe UI", 10),
                                   bg=BG, fg=FG, insertbackground=FG,
                                   relief="flat", bd=6)
        self._url_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._url_entry.bind("<Return>", lambda _: self._start_download())
        ttk.Button(ur, text="貼り付け", command=self._paste_url).pack(side="left", padx=(6, 0))
        ttk.Button(ur, text="クリア",
                   command=lambda: self._url_var.set("")).pack(side="left", padx=(4, 0))

        # Settings card
        sc = ttk.Frame(root, style="Card.TFrame", padding=14)
        sc.pack(fill="x", pady=(0, 10))

        ff = ttk.Frame(sc, style="Card.TFrame")
        ff.pack(fill="x", pady=(0, 8))
        ttk.Label(ff, text="保存先フォルダ", style="CardSub.TLabel").pack(anchor="w")
        fr = ttk.Frame(ff, style="Card.TFrame")
        fr.pack(fill="x", pady=(4, 0))
        default_dir = _config.get(OUTPUT_DIR_KEY,
                                   os.path.join(os.path.expanduser("~"), "Videos"))
        self._output_var = tk.StringVar(value=default_dir)
        tk.Entry(fr, textvariable=self._output_var,
                 font=("Segoe UI", 9),
                 bg=BG, fg=FG, insertbackground=FG,
                 relief="flat", bd=6).pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(fr, text="参照…", command=self._browse_folder).pack(side="left", padx=(6, 0))

        or_ = ttk.Frame(sc, style="Card.TFrame")
        or_.pack(fill="x")
        fmf = ttk.Frame(or_, style="Card.TFrame")
        fmf.pack(side="left", padx=(0, 20))
        ttk.Label(fmf, text="フォーマット", style="CardSub.TLabel").pack(anchor="w")
        self._format_var = tk.StringVar(value="H.264 MP4（推奨）")
        ttk.Combobox(fmf, textvariable=self._format_var,
                     values=["H.264 MP4（推奨）", "最高画質（H.265可）", "音声のみ MP3", "音声のみ M4A"],
                     state="readonly", width=20).pack(pady=(4, 0))

        qf = ttk.Frame(or_, style="Card.TFrame")
        qf.pack(side="left")
        ttk.Label(qf, text="最大解像度", style="CardSub.TLabel").pack(anchor="w")
        self._quality_var = tk.StringVar(value="制限なし")
        ttk.Combobox(qf, textvariable=self._quality_var,
                     values=["制限なし", "4K (2160p)", "2K (1440p)",
                              "FHD (1080p)", "HD (720p)", "SD (480p)"],
                     state="readonly", width=16).pack(pady=(4, 0))

        # Progress
        pc = ttk.Frame(root, style="Card.TFrame", padding=14)
        pc.pack(fill="x", pady=(0, 10))
        ph = ttk.Frame(pc, style="Card.TFrame")
        ph.pack(fill="x")
        ttk.Label(ph, text="進捗", style="CardSub.TLabel").pack(side="left")
        self._speed_label = tk.Label(ph, text="", font=("Segoe UI", 9), bg=CARD, fg=SUB)
        self._speed_label.pack(side="right")
        self._prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(pc, variable=self._prog_var, maximum=100,
                        style="Horizontal.TProgressbar").pack(fill="x", pady=(6, 4))
        self._prog_label = tk.Label(pc, text="待機中",
                                    font=("Segoe UI", 9), bg=CARD, fg=SUB)
        self._prog_label.pack(anchor="w")

        # Buttons
        br = ttk.Frame(root, style="TFrame")
        br.pack(fill="x", pady=(0, 10))
        self._dl_btn = ttk.Button(br, text="ダウンロード開始",
                                   style="Accent.TButton",
                                   command=self._start_download)
        self._dl_btn.pack(side="left", padx=(0, 8))
        self._cancel_btn = ttk.Button(br, text="キャンセル",
                                       command=self._cancel_download,
                                       state="disabled")
        self._cancel_btn.pack(side="left", padx=(0, 8))
        self._update_btn = ttk.Button(br, text="yt-dlp を更新",
                                       command=self._update_ytdlp)
        self._update_btn.pack(side="left", padx=(0, 8))
        ttk.Button(br, text="フォルダを開く",
                   command=self._open_output_folder).pack(side="right")

        # Log
        lf = ttk.Frame(root, style="Card.TFrame", padding=(10, 6))
        lf.pack(fill="both", expand=True)
        ttk.Label(lf, text="ログ", style="CardSub.TLabel").pack(anchor="w")
        tf = tk.Frame(lf, bg=CARD)
        tf.pack(fill="both", expand=True, pady=(4, 0))
        self._log = tk.Text(tf, font=("Consolas", 9),
                             bg="#13131f", fg=FG, relief="flat", bd=0,
                             wrap="word", state="disabled", height=8)
        sb = ttk.Scrollbar(tf, command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)
        self._log.tag_config("info",    foreground=FG)
        self._log.tag_config("success", foreground=SUCCESS)
        self._log.tag_config("warn",    foreground=WARN)
        self._log.tag_config("error",   foreground=ERR)
        self._log.tag_config("dim",     foreground=SUB)

        self._downloading = False
        self._cancel_flag = False
        self._ydl_ref = None

    # ── yt-dlp check ───────────────────────────────────
    def _check_ytdlp(self):
        if yt_dlp is None:
            self._ytdlp_badge.config(text="yt-dlp: 未インストール",
                                     fg=self._colors["ERR"])
            self._log_msg("yt-dlp が見つかりません。「yt-dlp を更新」ボタンでインストールしてください。",
                          "error")
            return
        ver = getattr(yt_dlp.version, "__version__", "不明")
        src = "libs/" if _YTDLP_SOURCE == "libs" else "内蔵"
        self._ytdlp_badge.config(text=f"yt-dlp {ver} ({src})",
                                 fg=self._colors["SUB"])
        self._log_msg(f"yt-dlp {ver} を検出しました ({src})。", "dim")

    # ── Helpers ────────────────────────────────────────
    def _log_msg(self, text, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] {text}\n", tag)
        self._log.configure(state="disabled")
        self._log.see("end")

    def _paste_url(self):
        try:
            self._url_var.set(self.clipboard_get().strip())
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
            os.startfile(folder)
        else:
            messagebox.showwarning("フォルダが見つかりません",
                                   f"フォルダが存在しません:\n{folder}")

    def _set_downloading(self, state: bool):
        self._downloading = state
        self._dl_btn.configure(state="disabled" if state else "normal")
        self._cancel_btn.configure(state="normal" if state else "disabled")

    # ── Format string ──────────────────────────────────
    def _build_format_string(self):
        fmt = self._format_var.get()
        qual = self._quality_var.get()
        hlim = {"4K (2160p)": 2160, "2K (1440p)": 1440,
                "FHD (1080p)": 1080, "HD (720p)": 720, "SD (480p)": 480}.get(qual)

        if fmt == "音声のみ MP3":
            return "bestaudio/best", {"postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]}
        if fmt == "音声のみ M4A":
            return "bestaudio[ext=m4a]/bestaudio/best", {}
        if fmt == "最高画質（H.265可）":
            f = (f"bestvideo[height<={hlim}]+bestaudio/best[height<={hlim}]/best"
                 if hlim else "bestvideo+bestaudio/best")
            return f, {}

        # H.264 MP4 (default)
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
                                 "yt-dlp が見つかりません。\n「yt-dlp を更新」ボタンでインストールしてください。")
            return
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning("URLが必要です", "ダウンロードするURLを入力してください。")
            return
        out = self._output_var.get().strip()
        if not out:
            messagebox.showwarning("保存先が必要です", "保存先フォルダを選択してください。")
            return
        os.makedirs(out, exist_ok=True)
        self._cancel_flag = False
        self._set_downloading(True)
        self._prog_var.set(0)
        self._prog_label.config(text="準備中…")
        self._speed_label.config(text="")
        threading.Thread(target=self._download_thread,
                         args=(url, out), daemon=True).start()

    def _cancel_download(self):
        self._cancel_flag = True
        self._log_msg("キャンセルを要求しました…", "warn")

    def _download_thread(self, url, out):
        fmt_str, extra = self._build_format_string()

        def hook(d):
            if self._cancel_flag:
                raise yt_dlp.utils.DownloadCancelled()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                dl = d.get("downloaded_bytes", 0)
                pct = dl / total * 100 if total else 0
                speed = d.get("speed")
                eta = d.get("eta")
                spd = _fmt_speed(speed) if speed else ""
                eta_s = f"  残り {_fmt_time(eta)}" if eta else ""
                fn = os.path.basename(d.get("filename", ""))
                self.after(0, self._update_progress,
                           pct, f"{fn}  {pct:.1f}%{eta_s}", spd)
            elif d.get("status") == "finished":
                self.after(0, self._update_progress, 100, "後処理中…", "")

        opts = {
            "format": fmt_str,
            "outtmpl": os.path.join(out, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "progress_hooks": [hook],
            "quiet": True,
        }
        opts.update(extra)
        self._log_msg(f"開始: {url}", "dim")
        try:
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
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _update_progress(self, pct, label, speed):
        self._prog_var.set(pct)
        self._prog_label.config(text=label)
        self._speed_label.config(text=speed)

    def _on_success(self, title, res, vcodec, filename):
        self._set_downloading(False)
        self._prog_var.set(100)
        self._prog_label.config(text="完了")
        self._speed_label.config(text="")
        self._log_msg(f"完了: {title}", "success")
        self._log_msg(f"  解像度: {res}  コーデック: {vcodec}", "dim")
        self._log_msg(f"  保存先: {filename}", "dim")

    def _on_cancelled(self):
        self._set_downloading(False)
        self._prog_var.set(0)
        self._prog_label.config(text="キャンセルされました")
        self._speed_label.config(text="")
        self._log_msg("ダウンロードをキャンセルしました。", "warn")

    def _on_error(self, msg):
        self._set_downloading(False)
        self._prog_var.set(0)
        self._prog_label.config(text="エラー")
        self._speed_label.config(text="")
        self._log_msg(f"エラー: {msg.splitlines()[-1] if msg else '不明'}", "error")
        self._log_msg("URLが正しいか、動画が公開されているか確認してください。", "warn")

    # ── yt-dlp updater ─────────────────────────────────
    def _update_ytdlp(self):
        self._update_btn.configure(state="disabled")
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
            self.after(0, self._update_btn.configure, {"state": "normal"})


# ──────────────────────────────────────────────────────
#  Utilities
# ──────────────────────────────────────────────────────
def _fmt_speed(bps: float) -> str:
    if bps >= 1_000_000:
        return f"{bps/1_000_000:.1f} MB/s"
    if bps >= 1_000:
        return f"{bps/1_000:.0f} KB/s"
    return f"{bps:.0f} B/s"


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
