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

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

async def main():
    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description="汎用Webドキュメント取得スクリプト")
    parser.add_argument(
        "--profile",
        default=None,
        help="ブラウザプロファイル名 (例: my_site_profile)。/data/<profile名> に保存される。"
    )
    args = parser.parse_args()

    print("🚀 汎用Webドキュメント取得スクリプトを開始します...")

    # スクリプトのディレクトリを基準にする
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 保存先ディレクトリの設定 (要件: ./result/general_scraped/)
    base_dir = os.path.dirname(script_dir) # 1つ上の階層
    output_dir = os.path.join(base_dir, "result", "general_scraped")
    os.makedirs(output_dir, exist_ok=True)
    print(f"📂 保存先ディレクトリ: {output_dir}")

    # watch_list.csv のパス
    csv_path = os.path.join(base_dir, "watch_list.csv")
    if not os.path.exists(csv_path):
        print(f"❌ エラー: {csv_path} が見つかりません。")
        print("フォーマット: [URL], [タイトル(任意)], [保存形式(mdまたはtxt)] の形式で作成してください。")
        return

    # CSV読み込みと対象URLリストの作成
    targets = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            
            url = row[0].strip()
            if not url or not url.startswith("http"): # httpから始まらない行（ヘッダーなど）は無視
                continue
            
            # 第2カラム（タイトル）が存在しない場合は空文字
            title = row[1].strip() if len(row) > 1 else ""
            # 第3カラム（保存形式）が存在しない場合は md とする
            fmt = row[2].strip().lower() if len(row) > 2 else "md"
            
            # 保存形式のバリデーション (不正な値は md にフォールバック)
            if fmt not in ["md", "txt"]:
                fmt = "md"
                
            # タイトルが空の場合、URLから安全な文字列を生成
            if not title:
                parsed = urlparse(url)
                # パス部分の最後の要素などをタイトルにする。空ならドメイン名を使用。
                path_parts = [p for p in parsed.path.split("/") if p]
                if path_parts:
                    title = path_parts[-1]
                else:
                    title = parsed.netloc
                # ファイル名として安全な文字に変換
                title = re.sub(r'[\\/*?:"<>|]', "_", title)
            
            targets.append({"url": url, "title": title, "fmt": fmt})

    if not targets:
        print("ℹ️ 処理対象のURLがありません。")
        return

    print(f"📋 合計 {len(targets)} 件のURLを処理します。")

    # --- 1. ブラウザ設定 ---
    # Persistent Context (ユーザーデータ永続化) 用のディレクトリ設定
    # 優先順位: コマンドライン引数 > 環境変数 > デフォルト値
    if args.profile:
        user_data_path = f"/data/{args.profile}"
    else:
        user_data_path = os.environ.get("PLAYWRIGHT_USER_DATA_DIR", "/data/default_profile")
    try:
        os.makedirs(user_data_path, exist_ok=True)
    except Exception as e:
        print(f"⚠️ ユーザーデータディレクトリ({user_data_path})の作成に失敗しました: {e}")
    
    browser_config = BrowserConfig(
        headless=False,  # ブラウザを表示 (Bot検知回避のため必須)
        verbose=True,
        user_data_dir=user_data_path, # ユーザーデータディレクトリ指定によりPersistent Contextとして起動
    )

    # --- 2. JSコード (展開 + 緩やかなスクロール) ---
    # あらゆるサイトの遅延読み込み（Lazy Load）対応、汎用的な展開ボタンのクリック
    expand_and_scroll_js = """
    (async () => {
        console.log("🟢 処理開始: 要素の展開と自動スクロール");
        
        // 1. 一般的な要素の展開
        document.querySelectorAll('details').forEach(el => el.open = true);
        document.querySelectorAll('[class*="expand"], [id*="expand"], .show-more, .read-more').forEach(el => {
            try { el.click(); } catch(e) {}
        });
        
        // 2. ページ最下部までの緩やかな自動スクロール
        await new Promise((resolve) => {
            let totalHeight = 0;
            const distance = 100;
            const timer = setInterval(() => {
                const scrollHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                totalHeight += distance;

                if (totalHeight >= scrollHeight - window.innerHeight) {
                    clearInterval(timer);
                    resolve();
                }
            }, 100); // 100msごとに100pxスクロール
        });
        
        // 3. スクロール完了後の追加待機 (遅延読み込み画像の完了待ち)
        console.log("⏳ スクロール完了、3秒待機中...");
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        console.log("🔴 待機完了");
    })();
    """

    # --- 3. クローラー実行 ---
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, target in enumerate(targets):
            url = target["url"]
            title = target["title"]
            fmt = target["fmt"]
            
            # 保存形式に応じてMarkdownGeneratorの設定を変える
            # txt形式: リンク・画像に加え、見出しや強調などのMarkdown記号も除去し
            #          プレーンテキストとして出力する（Crawl4AIパーサー側で制御）
            if fmt == "txt":
                md_generator = DefaultMarkdownGenerator(options={
                    "ignore_links": True,
                    "ignore_images": True,
                    "skip_internal_links": True,
                    "include_sup_sub": False,
                    "escape_misc": False,
                    "escape_dot": False,
                    "escape_plus": False,
                    "escape_dash": False,
                    "heading_style": "SETEXT_NEVER",
                })
            else:
                md_generator = DefaultMarkdownGenerator()

            # URLごとにconfigを生成
            config = CrawlerRunConfig(
                js_code=[expand_and_scroll_js],
                delay_before_return_html=3.0,
                wait_until="domcontentloaded", # ページロード完了を待機
                markdown_generator=md_generator,
                cache_mode=CacheMode.BYPASS, # キャッシュ無効化で常に最新を取得
            )

            print(f"\n[{i+1}/{len(targets)}] 🔍 処理中: {url}")
            print(f"   => 保存予定: {title}.{fmt}")
            
            try:
                # ページ取得の実行
                result = await crawler.arun(url=url, config=config)
                
                if result.success:
                    # fit_markdown（主要コンテンツ）を優先、なければraw_markdown
                    content = result.markdown.fit_markdown or result.markdown.raw_markdown
                    
                    if not content:
                        print(f"⚠️ コンテンツを取得できませんでした: {url}")
                        continue

                    # 保存形式による処理の分岐
                    if fmt == "txt":
                        # MarkdownGenerator側でほとんどの記号は除去済み
                        # 残存する最小限の記号のみ後処理で除去する
                        content = re.sub(r'(?m)^#+\s', '', content)  # 見出し(#)の残存分
                        content = content.strip()

                    save_name = f"{title}.{fmt}"
                    save_path = os.path.join(output_dir, save_name)
                    
                    # 取得内容の保存
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(content)
                        
                    print(f"✅ 保存完了: {save_path}")
                else:
                    print(f"❌ 失敗: {url}")
                    print(f"   理由: {result.error_message}")
            
            except Exception as e:
                # タイムアウト等のエラー発生時も停止せずに継続
                print(f"🚨 エラー発生: {url}")
                print(f"   詳細: {e}")
            
            # 最後のURL以外はランダム待機 (Bot検知回避)
            if i < len(targets) - 1:
                wait_sec = random.uniform(5, 15)
                print(f"🕒 Bot検知回避のため {wait_sec:.1f} 秒待機します...")
                await asyncio.sleep(wait_sec)

    print("\n🎉 すべての処理が完了しました！")

if __name__ == "__main__":
    asyncio.run(main())
