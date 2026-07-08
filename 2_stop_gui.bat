@echo off
chcp 65001 > nul

echo.
echo === GUI付きChromeコンテナを停止します (コンテナは削除しません)... ===
echo.

rem // docker-compose stopコマンドでコンテナを停止します
docker-compose stop

if %errorlevel% neq 0 (
    echo.
    echo X 停止コマンドの送信に失敗しました。
    pause
    exit /b
)

echo.
echo === 停止処理が完了しました ===
echo 次回「1_start_gui.bat」を実行した際、ビルドがスキップされ高速に起動します。
echo.

pause
