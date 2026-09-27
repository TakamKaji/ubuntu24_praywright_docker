# Web Crawling & Markdown Suite (Docker Edition)

Ubuntu 24.04 + XFCE/RDP + Google Chrome Stable + Playwright をまとめた、ローカルPC常駐向けの収集環境です。
汎用スクレイパーに加えて、ログイン済みの通常Google Chromeを使う `note.com` 専用collectorを搭載しています。

## note collector

### 目的

note.com の監視対象から新着記事だけを取得し、次の自己完結形式で保存します。

```text
result/note/
├─ latest_status.json
├─ index.json
└─ YYYY-MM-DD_<note-id>/
   ├─ <記事タイトル>.md
   ├─ metadata.json
   └─ images/
      ├─ 001.webp
      ├─ 002.jpg
      └─ ...
```

画像は原則として配信元の形式を維持します。Markdown内の画像URLは `images/001.webp` のようなローカル相対パスへ置換されます。
既に取得済みの記事は `index.json` を基準にskipし、一覧側で更新日時が新しくなった記事だけ再取得します。

### 構成

- ブラウザ: Docker内の `google-chrome-stable`
- profile: `/data/chrome-profile` (Docker named volumeで永続化)
- 操作: Playwrightが起動済みChromeへCDP接続
- Markdown化: Crawl4AI `DefaultMarkdownGenerator`
- 巡回: Supervisor上の `note_collector.py --daemon`
- 既定間隔: 1800秒
- 保存先: `./result/note`

Playwright自身のChromiumはnoteログインには使用しません。初回ログインも巡回も同じGoogle Chrome profileを使います。

## 初回セットアップ

1. `1_start_gui.bat` を実行してDockerをbuild/startします。
2. RDPへ `dockeruser / password` でログインします。
3. デスクトップの **Google Chrome (note collector)** を起動します。
4. Chrome上でnote.comへ人間が手動ログインします。
5. `note_watch_list.csv` に監視URLを追加します。

Chromeは次の条件で起動します。

```text
google-chrome-stable
  --user-data-dir=/data/chrome-profile
  --remote-debugging-port=9222
  --remote-debugging-address=127.0.0.1
```

CDPポート9222はDockerホストへ公開しません。

## 監視対象

`note_watch_list.csv`:

```csv
# name,url
market_report,https://note.com/example
```

クリエイターページ、マガジン等の記事一覧URLを指定できます。
単独の記事URLを指定して1件だけ管理することもできます。

## 自動巡回

`note-collector` はSupervisorから常駐起動されます。

Chromeが起動していない間は記事取得を行わず、

```json
{"status": "browser_down"}
```

を `result/note/latest_status.json` に記録します。

Chromeが起動してnoteにログイン済みなら、既定では30分ごとに新着を確認します。
間隔はホスト側で `NOTE_POLL_SECONDS` を設定して変更できます。

PowerShell例:

```powershell
$env:NOTE_POLL_SECONDS="3600"
docker compose up -d --build
```

### 今すぐ1回取得

Windowsでは `3_note_fetch_now.bat` を実行します。

または:

```bash
docker compose exec -T ubuntu-vnc \
  /opt/venv/bin/python /app/code/note_collector.py --once
```

常駐collectorと同時実行になった場合はlockにより二重取得を防止します。

## ステータス

`result/note/latest_status.json` の主な状態:

- `idle`: `note_watch_list.csv` に監視先がない
- `browser_down`: Google Chrome/CDPへ接続できない
- `auth_required`: noteの再ログインが必要
- `running`: 取得処理中
- `ok`: 正常完了
- `partial_error`: 一部の記事または監視URLで失敗

コンテナログも確認できます。

```bash
docker compose logs -f ubuntu-vnc
```

## 保存内容

`metadata.json` には最低限以下を保存します。

- source URL
- note ID
- 記事タイトル
- 公開日時
- 更新日時
- 取得日時
- Markdownファイル名
- 保存画像と元URL
- 画像取得エラー

記事ファイル名には記事タイトルを使用し、Windowsで使えない文字だけ除去します。
フォルダ名は `<公開日>_<note-id>` なので、同名記事でも衝突しません。

## 既存の汎用スクレイパー

既存の `url_seeder_generic.py` と `universal_fetcher.py` は残しています。
従来用途では `Playwright Browser` を使用できますが、note collectorは **Google Chrome (note collector)** を使用してください。

## セッション永続化

noteのCookie/profileはDocker volumeの `/data/chrome-profile` に保存されるため、通常のコンテナstop/startでは維持されます。
ただしnoteまたは認証側でセッションが失効した場合は、RDPからGoogle Chromeを開いて再ログインしてください。
collector自身はログイン操作を自動化しません。

## セキュリティ

本環境はローカルPCでの個人利用を前提としています。

- RDPは `127.0.0.1:3390` のみにbindします。
- Chrome CDPの9222番はDocker外へ公開しません。
- `/data/chrome-profile` にはログインCookieが含まれるため、バックアップや共有には注意してください。
- `dockeruser` / `root` の既定パスワードは `password` です。外部公開環境では使用しないでください。

## 今後の拡張

collectorの定期実行はDocker内だけで完結させ、ChatGPT/MCPには依存させません。
将来MCP Serverを追加する場合は `latest_status.json` とcollectorのcommandを利用して、
`health`, `latest_status`, `fetch_now`, `retry_article`, `sync_drive` を提供する想定です。
