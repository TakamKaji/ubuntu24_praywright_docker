# GUI RDP & Selenium 連携 Chrome on Docker

ブラウザ自動操作 (Selenium) を、**日本語入力が可能なGUI（リモートデスクトップ）**で確認しながら実行できる Docker コンテナ環境です。

`docker-compose` を使って、Ubuntu 22.04 + XFCEデスクトップ環境を構築します。
ChromeはSeleniumのデバッグモード (ポート `9222`) で起動し、ホストPCのWindowsからRDP (リモートデスクトップ接続) でGUIにアクセスできます。

## ✨ 特徴

* **RDP接続:** VNCではなく、Windows標準のリモートデスクトップクライアント (`mstsc`) で接続できます。
* **日本語入力対応:** RDP経由で **Mozc による日本語入力（ローマ字入力）**が可能です。
* **Selenium連携:** 起動したChromeのGUIを、Selenium (Python) スクリプトから直接操作できます。
* **データ永続化:** Chromeのプロファイル (`/data`) はDockerボリュームに保存されるため、コンテナを再起動しても設定やCookieが保持されます。
* **Windows用バッチファイル:** Windowsユーザーが簡単に操作できるよう、各種バッチファイルが同梱されています。

---

## 💻 前提条件

* **Docker Desktop**
    * Windowsにインストールされている必要があります。
    * `docker-compose` コマンドが使用できることが前提です (Docker Desktopに同梱されています)。
* **リモートデスクトップクライアント**
    * Windowsに標準搭載されている `mstsc.exe` を使用します。

---

## 🚀 使い方 (GUIの起動)

1.  このリポジトリをクローン、またはZIPでダウンロードします。
2.  `1_start_gui.bat` をダブルクリックして実行します。
3.  Dockerイメージのビルドとコンテナの起動が自動的に行われます。
4.  ビルド完了後、Windowsのリモートデスクトップ接続が自動で起動します。
5.  ログイン画面で、以下の情報を入力してログインします。
    * **ユーザー名:** `dockeruser`
    * **パスワード:** `password`
6.  Linuxデスクトップが表示されたら、デスクトップ上の `Launch Google Chrome` アイコンをダブルクリックしてChromeを起動します。
7.  （日本語入力は、パネルのキーボードアイコン（または「あ」）をクリックして「日本語 - Mozc」を選択することでオン/オフできます）

---

## 🐍 Selenium からの操作

RDPで起動したChromeは、ポート `9222` でデバッグ接続を待ち受けています。
ホストPC（Windows側）のPythonスクリプトから、以下のように接続できます。

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- 既存のChromeに接続する設定 ---
options = Options()
options.add_experimental_option("debuggerAddress", "localhost:9222")
# -------------------------------------

print("起動中のChromeに接続します...")
driver = webdriver.Chrome(options=options)

# これで、RDPで見ているGUI上のChromeを操作できます
print(f"現在のページのタイトル: {driver.title}")

# driver.quit() は呼び出さないでください (ブラウザが閉じてしまいます)
```

### サンプルスクリプト

* `code/save_pdfs.py`:
    現在開いているページとiFrame内のすべてのリンクをスキャンし、PDFファイルをコンテナ内の `/home/dockeruser/downloads` フォルダにダウンロードします。

---

## 🛠️ 同梱スクリプト一覧

### メイン操作

* `1_start_gui.bat`:
    コンテナをビルドして起動し、RDPクライアントを立ち上げます。
* `2_stop_gui.bat`:
    コンテナを停止します（データは消えません）。

### サンプル操作

* `4_save_pdfs.bat`:
    コンテナ内で `save_pdfs.py` を実行し、RDP上のChromeで表示しているページのPDFをダウンロードします。
* `5_copy_downloads_folder.bat`:
    `4_save_pdfs.bat` でダウンロードしたファイルを、コンテナの `/home/dockeruser/downloads` からホストPC（Windows）の `./downloads` フォルダにコピーします。

---

## ⚙️ 詳細設定

* **RDPポート:** `localhost:3390`
* **Seleniumポート:** `localhost:9222`
* **RDPログイン:** `dockeruser` / `password`
* **プロジェクトフォルダ (コンテナ内):** `/app` (ホストのカレントディレクトリがマウントされます)
* **Chromeプロファイル (コンテナ内):** `/data` (Dockerボリューム `chrome-profile` に保存されます)
* **ダウンロードパス (コンテナ内):** `/home/dockeruser/downloads`