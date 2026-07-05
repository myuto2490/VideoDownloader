"""アプリアイコン (icon.ico / icon_64.png) を生成するスクリプト。

実行: python make_icon.py
デザイン: 紫のグラデーション角丸背景 + 白いダウンロード矢印 + トレイ
"""
import base64
import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
SIZE = 256


def make_base(size: int = SIZE) -> Image.Image:
    ss = 4  # スーパーサンプリング倍率
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 縦グラデーションの角丸四角形
    top = (139, 92, 246)     # #8b5cf6
    bottom = (109, 40, 217)  # #6d28d9
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        gd.line([(0, y), (s, y)], fill=c + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 4.5, fill=255)
    img.paste(grad, (0, 0), mask)

    w = s
    white = (255, 255, 255, 255)

    # ダウンロード矢印（軸 + 三角形）
    shaft_w = w * 0.13
    cx = w / 2
    d.rounded_rectangle(
        [cx - shaft_w / 2, w * 0.20, cx + shaft_w / 2, w * 0.46],
        radius=shaft_w / 2, fill=white)
    d.polygon(
        [(cx - w * 0.19, w * 0.44), (cx + w * 0.19, w * 0.44), (cx, w * 0.62)],
        fill=white)

    # トレイ
    lw = round(w * 0.055)
    tray_y = w * 0.72
    d.line([(w * 0.24, tray_y), (w * 0.24, w * 0.79)], fill=white, width=lw)
    d.line([(w * 0.24, w * 0.79), (w * 0.76, w * 0.79)], fill=white, width=lw)
    d.line([(w * 0.76, w * 0.79), (w * 0.76, tray_y)], fill=white, width=lw)
    # 角を丸く
    r = lw / 2
    for x, y in [(w * 0.24, tray_y), (w * 0.76, tray_y),
                 (w * 0.24, w * 0.79), (w * 0.76, w * 0.79)]:
        d.ellipse([x - r, y - r, x + r, y + r], fill=white)

    return img.resize((size, size), Image.LANCZOS)


def main():
    img = make_base()
    ico_path = os.path.join(BASE, "icon.ico")
    img.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", ico_path)

    png64 = img.resize((64, 64), Image.LANCZOS)
    png_path = os.path.join(BASE, "icon_64.png")
    png64.save(png_path)
    print("wrote", png_path)

    # tkinter 埋め込み用 base64 を出力
    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    out = os.path.join(BASE, "icon_b64.txt")
    with open(out, "w") as f:
        f.write(b64)
    print("wrote", out, f"({len(b64)} chars)")


if __name__ == "__main__":
    main()
