@echo off
chcp 65001 > nul

echo.
echo === RDP版 GUI付きChromeコンテナの準備を開始します ===
echo.
rem // ステップ1: コンテナをビルド & 起動
docker-compose up -d --build
if %errorlevel% neq 0 (
    echo.
    echo X コンテナの起動に失敗しました。
    pause
    exit /b
)
echo.
echo === ステップ1/2: コンテナの起動に成功しました ===
echo.
echo 5秒後にリモートデスクトップ接続を起動します...
timeout /t 5 > nul

rem // ステップ2: ホストPCのリモートデスクトップクライアントを起動する
echo.
echo === ステップ2/2: リモートデスクトップ接続を起動しています... ===
rem // mstsc.exe はWindowsのリモートデスクトップクライアントです
start mstsc /v:localhost:3390

echo.
echo "----------------------------------------------------"
echo.
echo   全ての準備処理が完了しました！
echo.
echo   リモートデスクトップの画面で、以下の情報を入力してログインしてください。
echo   - ユーザー名: dockeruser
echo   - パスワード: password (Dockerfileで設定したもの)
echo.
echo   ログイン後、デスクトップ上の「Launch Google Chrome」アイコンを
echo   ダブルクリックして、Chromeを起動してください。
echo.
echo "----------------------------------------------------"
echo.

rem // このウィンドウは手動で閉じてください
pause