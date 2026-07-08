import argparse
import asyncio
import csv
import os
import re
import sys
import random
from urllib.parse import urlparse

# Windowsのコンソール出力での文字化け対策
sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright

# --- 定数設定 ---
MAX_PAGES = 20          # 1カテゴリ（シードURL）あたりの最大探索ページ数
WAIT_MIN = 1.0          # アクセス間の待機時間（最小）
WAIT_MAX = 3.0          # アクセス間の待機時間（最大）

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
WATCH_LIST_CSV = os.path.join(BASE_DIR, "watch_list.csv")
# ホスト側と同期しない隔離ボリューム(/data)をデフォルトとする
DEFAULT_USER_DATA_DIR = os.environ.get("PLAYWRIGHT_USER_DATA_DIR", "/data/default_profile")

def get_safe_title(url: str) -> str:
    """URLから安全なファイル名（タイトル）を生成する"""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split('/') if p]
    base_name = parts[-1] if parts else parsed.netloc
    # 英数字と一部の記号以外はアンダースコアに置換
    safe_name = re.sub(r'[\\/*?:"<>|]', "_", base_name)
    return safe_name

async def main():
    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description="汎用URLシーダー")
    parser.add_argument(
        "--profile",
        default=None,
        help="ブラウザプロファイル名 (例: my_site_profile)。/data/<profile名> に保存される。"
    )
    args = parser.parse_args()

    # 優先順位: コマンドライン引数 > 環境変数 > デフォルト値
    user_data_dir = f"/data/{args.profile}" if args.profile else DEFAULT_USER_DATA_DIR

    print("🚀 汎用URLシーダーを開始します...")
    
    seeds = []
    
    # 1. watch_list.csv の読み込み、または標準入力による作成
    if not os.path.exists(WATCH_LIST_CSV):
        print(f"\nℹ️ {WATCH_LIST_CSV} が見つかりません。新規作成のための情報を入力してください。")
        seed_url = input("探索を開始する基準URLを入力してください (例: https://example.com/): ").strip()
        category = input("カテゴリ名（出力フォルダ名になります）を入力してください [デフォルト: default]: ").strip() or "default"
        ext = input("保存形式 (md または txt) [デフォルト: md]: ").strip() or "md"
        
        if seed_url:
            # 入力された情報でCSVを新規作成
            with open(WATCH_LIST_CSV, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([seed_url, category, ext])
            seeds.append({"url": seed_url, "category": category, "ext": ext})
            print(f"✅ {WATCH_LIST_CSV} を作成しました。")
        else:
            print("❌ 基準URLが入力されなかったため、処理を終了します。")
            return
    else:
        # 既存のCSVから読み込み
        with open(WATCH_LIST_CSV, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                url = row[0].strip()
                if not url or url.startswith("#") or not url.startswith("http"):
                    continue
                category = row[1].strip() if len(row) > 1 else "default"
                ext = row[2].strip() if len(row) > 2 else "md"
                seeds.append({"url": url, "category": category, "ext": ext})
                
    if not seeds:
        print("❌ 探索対象のURL（シード）がありません。")
        return

    try:
        os.makedirs(user_data_dir, exist_ok=True)
    except Exception as e:
        print(f"⚠️ ユーザーデータディレクトリ({user_data_dir})の作成に失敗しました: {e}")

    # 2. Playwrightの起動（Persistent Contextによるセッション共有）
    async with async_playwright() as p:
        print(f"📂 User Data Dir: {user_data_dir}")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False, # Bot検知回避のためブラウザを表示
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            args=["--disable-gpu", "--no-sandbox"]
        )
        
        # 既存のページがあればそれを使い、なければ新規作成
        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        # 3. シードごとに探索を実行
        for seed in seeds:
            base_url = seed["url"]
            category = seed["category"]
            ext = seed["ext"]
            
            parsed_base = urlparse(base_url)
            base_domain = parsed_base.netloc
            
            print(f"\n{'='*50}")
            print(f"🔍 探索開始: {base_url}")
            print(f"   カテゴリ: {category}")
            print(f"   ターゲットドメイン: {base_domain}")
            
            # 結果保存先の準備
            out_dir = os.path.join(SCRIPT_DIR, "result", category)
            os.makedirs(out_dir, exist_ok=True)
            out_csv = os.path.join(out_dir, "url_list.csv")
            
            # 既存のURLを読み込み、重複を排除するためのSetを用意
            saved_urls = set()
            if os.path.exists(out_csv):
                with open(out_csv, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and row[0].startswith("http"):
                            saved_urls.add(row[0].strip())
            print(f"   既存の収集済みURL数: {len(saved_urls)}件")
            
            # 探索用キューと状態管理
            queue = [base_url]
            visited_urls = set()
            pages_crawled = 0
            new_urls_found = []

            # BFS（幅優先探索）ループ
            while queue and pages_crawled < MAX_PAGES:
                current_url = queue.pop(0)
                
                # すでに訪問済みならスキップ
                if current_url in visited_urls:
                    continue
                
                visited_urls.add(current_url)
                pages_crawled += 1
                
                # 進捗表示
                print(f"[{pages_crawled}/{MAX_PAGES}] 🌐 アクセス中: {current_url}")
                
                try:
                    # ページへ移動してロード完了を待機
                    await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
                    
                    # ページ内の全 <a> タグからリンクを抽出（JSレイヤーでの実行）
                    extracted_hrefs = await page.evaluate("""() => {
                        const links = Array.from(document.querySelectorAll('a'));
                        const uniqueLinks = new Set();
                        links.forEach(a => {
                            if (a.href) {
                                // フラグメント（#）以降を除去して一意にする
                                uniqueLinks.add(a.href.split('#')[0]);
                            }
                        });
                        return Array.from(uniqueLinks);
                    }""")
                    
                    # 抽出したリンクのフィルタリング
                    for href in extracted_hrefs:
                        href = href.rstrip('/') # 最後にスラッシュがあれば除去
                        parsed_href = urlparse(href)
                        
                        # 同一ドメインかつ http/https のみを対象とする
                        if parsed_href.scheme in ["http", "https"] and parsed_href.netloc == base_domain:
                            # まだ訪問しておらず、キューにも入っていなければ探索対象に追加
                            if href not in visited_urls and href not in queue:
                                queue.append(href)
                            
                            # まだファイルに保存されていない新しいURLであれば追加対象とする
                            if href not in saved_urls:
                                saved_urls.add(href)
                                title = get_safe_title(href)
                                new_urls_found.append([href, title, ext])
                                
                except Exception as e:
                    print(f"   ⚠️ アクセスエラー: {e}")
                
                # 次のページへ行く前に節度を持った待機（ランダムウェイト）
                if queue and pages_crawled < MAX_PAGES:
                    wait_time = random.uniform(WAIT_MIN, WAIT_MAX)
                    # print(f"   🕒 Bot検知回避・負荷軽減のため {wait_time:.1f}秒待機します...")
                    await asyncio.sleep(wait_time)

            # --- 探索結果の保存 ---
            if new_urls_found:
                print(f"\n✨ 【完了】{len(new_urls_found)}件の新規URLを発見しました！")
                # 重複を除いて追記保存
                with open(out_csv, "a", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(new_urls_found)
                print(f"💾 追記保存完了: {out_csv}")
            else:
                print(f"\nℹ️ 【完了】新規URLは見つかりませんでした（すでに全件取得済み、またはリンクがありません）。")
        
        print("\nブラウザを閉じます...")
        await context.close()
        print("🎉 すべての探索プロセスが完了しました！")

if __name__ == "__main__":
    asyncio.run(main())
