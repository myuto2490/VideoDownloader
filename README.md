# Video Downloader

[![release](https://img.shields.io/github/v/release/myuto2490/VideoDownloader?label=release&color=0A84FF)](https://github.com/myuto2490/VideoDownloader/releases/latest)
[![License](https://img.shields.io/badge/License-MIT-2ea44f)](LICENSE)
[![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-0078D6)](https://github.com/myuto2490/VideoDownloader/releases/latest)

URL を貼り付けるだけで動画・音声を保存できるデスクトップアプリです（**Windows / macOS 対応**）。
[yt-dlp](https://github.com/yt-dlp/yt-dlp) を内蔵し、Apple Human Interface Guidelines に沿ったダークテーマの GUI で操作できます。

![screenshot](docs/screenshot.png)

## ダウンロード（利用者向け）

### Windows

環境構築は不要です。Python のインストールも必要ありません。

1. [Releases](../../releases/latest) から `VideoDownloader.zip` をダウンロード
2. 好きな場所に展開して `VideoDownloader.exe` を実行

これだけで動画の保存・結合・MP3 変換まですべて使えます。
**ffmpeg も zip に同梱**されているため、追加のインストールは一切不要です。

> 万一 ffmpeg が見つからない環境（exe 単体をコピーした場合など）でも、
> 初回起動時に [yt-dlp 公式ビルド](https://github.com/yt-dlp/FFmpeg-Builds) を
> 自動ダウンロードしてセットアップします。

### macOS

いちばん簡単なのは **ランチャーをダブルクリックする** 方法です。

1. このリポジトリを取得（`git clone` または「Code ▸ Download ZIP」で展開）
2. `run_mac.command` を **ダブルクリック**

初回だけ、必要なもの（`yt-dlp` と `ffmpeg`）を自動でセットアップしてから起動します。
2 回目以降はすぐ起動します。

- ffmpeg は [Homebrew](https://brew.sh) があれば `brew install ffmpeg` で導入し、
  無ければアプリ内で自動ダウンロードします。
- GUI 表示に新しい Tk が必要な場合、ランチャーが `python-tk` を自動導入します。

> **`"開発元を確認できないため開けません"` と出たら**
> `run_mac.command` を **右クリック →「開く」** を選ぶと、以降ふつうに起動できます。
> （ダウンロードしたスクリプトに対する macOS の初回確認です）

macOS を単体の **`.app`** にまとめたい場合は、下記「[macOS の .app をビルド](#macos-の-app-をビルド)」を参照してください。

## 主な機能

- URL 貼り付け（クリップボード自動検出）だけの簡単操作
- フォーマット選択: MP4 / 最高画質 / MP3 / M4A
- 最大解像度の指定（480p〜4K）
- ダウンロードの進行状況表示（％・サイズ・速度・残り時間・処理段階）
- 実行ログ表示

## yt-dlp の更新について

YouTube などのサイトは仕様が頻繁に変わるため、**yt-dlp は定期的な更新が必要**です。
このアプリはアプリ本体を再インストールせずに yt-dlp だけを更新できます。

- 起動時に新バージョンを自動チェックし、右上のバッジとログでお知らせします
- 右上の **🔄 ボタン** を押すと、PyPI から最新の yt-dlp をダウンロードして
  exe と同じフォルダの `libs/` に展開します（アプリ再起動後に有効）
- `libs/` のコピーが壊れている場合は、exe 内蔵のバージョンに自動フォールバックします

## 開発者向け

### 必要環境

- Python 3.9+（Windows のビルドは 3.13。macOS は Tk 8.6 が使える Python 推奨）
- `pip install yt-dlp pyinstaller`
- 動画の結合・MP3 変換に `ffmpeg`（無ければアプリが自動取得）

> `video_downloader.py` は Windows / macOS / Linux 共通の 1 ファイルです。
> フォント・ffmpeg の取得先・保存先フォルダを開く処理などを OS ごとに切り替えます。

### ソースから実行

```sh
python video_downloader.py
```

macOS では `run_mac.command` をダブルクリックすると、仮想環境の作成・
`yt-dlp` / `ffmpeg` の用意・起動までを自動で行います。

### exe のビルド（Windows）

```sh
python -m PyInstaller VideoDownloader.spec --noconfirm
```

`dist/VideoDownloader.exe` が生成されます。

### macOS の .app をビルド

```sh
./build_mac.sh
```

`dist/VideoDownloader.app` が生成されます（内部で `make_icns.py` により
`icon.icns` を生成し、`VideoDownloader-mac.spec` でビルドします）。
未署名アプリのため、初回は右クリック →「開く」、または
`xattr -dr com.apple.quarantine dist/VideoDownloader.app` で許可してください。

### リリース手順（バージョン管理）

1. `video_downloader.py` の `APP_VERSION` を更新
2. コミットしてタグを打つ:

   ```sh
   git tag v1.0.1
   git push origin main --tags
   ```

3. GitHub Actions が自動で exe をビルドし、Release に `VideoDownloader.zip` を添付します

## 免責事項

本アプリは私的利用の範囲でご使用ください。ダウンロードするコンテンツの権利・
各サービスの利用規約は利用者自身の責任で確認してください。

## ライセンス

[MIT License](LICENSE)

本アプリは [yt-dlp](https://github.com/yt-dlp/yt-dlp)（Unlicense）を利用しています。
同梱の ffmpeg バイナリは [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds)
のビルド（GPL）です。ライセンス全文は zip 内の `FFMPEG_LICENSE.txt` を参照してください。
