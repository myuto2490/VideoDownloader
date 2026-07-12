# Video Downloader

URL を貼り付けるだけで動画・音声を保存できる Windows 用デスクトップアプリです。
[yt-dlp](https://github.com/yt-dlp/yt-dlp) を内蔵し、Apple Human Interface Guidelines に沿ったダークテーマの GUI で操作できます。

![screenshot](docs/screenshot.png)

## ダウンロード（利用者向け）

環境構築は不要です。Python のインストールも必要ありません。

1. [Releases](../../releases/latest) から `VideoDownloader.zip` をダウンロード
2. 好きな場所に展開して `VideoDownloader.exe` を実行

> **注意:** 高画質動画の保存（映像+音声の結合）や MP3 変換には [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) が必要です。
> `ffmpeg.exe` を PATH の通った場所に置くか、`VideoDownloader.exe` と同じフォルダに置いてください。

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

- Python 3.11+（開発は 3.13）
- `pip install yt-dlp pyinstaller`

### ソースから実行

```
python video_downloader.py
```

### exe のビルド

```
python -m PyInstaller VideoDownloader.spec --noconfirm
```

`dist/VideoDownloader.exe` が生成されます。

### リリース手順（バージョン管理）

1. `video_downloader.py` の `APP_VERSION` を更新
2. コミットしてタグを打つ:

   ```
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
