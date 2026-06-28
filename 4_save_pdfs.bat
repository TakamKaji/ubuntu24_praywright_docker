@echo off
chcp 65001 > nul

echo.
echo === 表示中のページのPDFを全てダウンロードします... ===
echo.

docker-compose exec -u dockeruser chrome-vnc mkdir -p /home/dockeruser/downloads

rem // Pythonスクリプトを実行 (dockeruserで)
docker-compose exec -u dockeruser chrome-vnc python3 /app/code/save_pdfs.py

echo.
echo === 処理が完了しました ===
echo ダウンロードされたファイルは、コンテナ内の "/home/dockeruser/downloads" フォルダにあります。
echo.
echo ファイルを取り出すには、以下のコマンドを実行してください:
echo docker-compose cp chrome-vnc:/home/dockeruser/downloads/ファイル名 .
echo.

pause