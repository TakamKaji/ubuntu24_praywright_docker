#!/bin/bash
source /opt/venv/bin/activate
echo "Playwright Browserを起動します..."

python3 -c "
import asyncio
from playwright.async_api import async_playwright

async def main():
    try:
        async with async_playwright() as p:
            print('ブラウザを起動中...')
            browser = await p.chromium.launch_persistent_context(
                user_data_dir='/data/note_profile',
                headless=False,
                args=['--disable-gpu', '--no-sandbox'],
                viewport={'width': 1280, 'height': 800}
            )
            # persistent_contextの場合はデフォルトページが1つ開いていることが多い
            pages = browser.pages
            page = pages[0] if len(pages) > 0 else await browser.new_page()
            
            await page.goto('https://note.com/')
            print('✅ 起動しました。この黒いウィンドウを閉じるとブラウザも終了します。')
            await asyncio.Event().wait()
            
    except Exception as e:
        print(f'\n❌ エラーが発生しました:\n{e}\n')

asyncio.run(main())
"

echo "ブラウザのプロセスが終了しました。"
read -p "Enterを押してこの画面を閉じます..."