#!/usr/bin/env python3
"""video_downloader.py に埋め込まれた PNG アイコンから macOS 用 icon.icns を生成する。

macOS 標準の `sips` / `iconutil` を使うため、追加ライブラリは不要。
元画像が 64x64 のため大サイズは拡大表示になるが、.app のアイコンとして機能する。

    python3 make_icns.py   ->  icon.icns
"""
import base64
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "video_downloader.py")
OUT = os.path.join(HERE, "icon.icns")


def _extract_b64() -> bytes:
    """video_downloader.py 内の _ICON_B64 = ( "..." "..." ) を取り出す。"""
    with open(SRC, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"_ICON_B64\s*=\s*\((.*?)\)", text, re.DOTALL)
    if not m:
        sys.exit("video_downloader.py 内に _ICON_B64 が見つかりませんでした。")
    b64 = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    return base64.b64decode(b64)


def main():
    if sys.platform != "darwin":
        sys.exit("make_icns.py は macOS 専用です（sips / iconutil を使用）。")

    png_bytes = _extract_b64()
    with tempfile.TemporaryDirectory() as tmp:
        base_png = os.path.join(tmp, "icon.png")
        with open(base_png, "wb") as f:
            f.write(png_bytes)

        iconset = os.path.join(tmp, "icon.iconset")
        os.makedirs(iconset, exist_ok=True)

        # macOS が要求する iconset のサイズ一式
        specs = [
            (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
        ]
        for size, name in specs:
            subprocess.run(
                ["sips", "-z", str(size), str(size), base_png,
                 "--out", os.path.join(iconset, name)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", OUT],
                       check=True)
    print(f"生成しました: {OUT}")


if __name__ == "__main__":
    main()
