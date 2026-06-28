@echo off
chcp 65001 > nul

echo.
echo === コンテナ内のダウンロードフォルダからファイルを取得します... ===
echo.

rem // ホストPC側（このバッチファイルと同じ階層）に "downloads" フォルダがなければ作成
if not exist "downloads" (
    echo "downloads" フォルダを作成します...
    mkdir "downloads"
)

rem // docker-compose cp コマンドで、コンテナの /home/dockeruser/downloads の中身を
rem // ホストPCの "downloads" フォルダにコピーします
docker-compose cp chrome-vnc:/home/dockeruser/downloads/. ./downloads/

if %errorlevel% neq 0 (
    echo.
    echo X ファイルのコピーに失敗しました。
    echo X まず「1_start_gui.bat」でコンテナが起動しているか確認してください。
    pause
    exit /b
)

echo.
echo === ファイルのコピーが完了しました ===
echo このフォルダ（バッチファイルのある場所）の "downloads" フォルダを確認してください。
echo.

pause