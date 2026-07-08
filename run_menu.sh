#!/bin/bash

# カレントディレクトリをこのファイルの場所に固定
cd "$(dirname "$0")"

# 仮想環境の読み込み (Dockerコンテナ内のパス)
if [ -f "/opt/venv/bin/activate" ]; then
    source /opt/venv/bin/activate
fi

# 無限ループでメニューを表示
while true; do
    clear
    echo "======================================================"
    echo "       Web Crawling & Markdown Merging Suite"
    echo "======================================================"
    echo ""

    # 配列の初期化
    declare -a FILE_LIST
    declare -a TITLE_LIST
    COUNT=0

    # codeフォルダが存在しない場合のエラーハンドリング
    if [ ! -d "code" ]; then
        echo "❌ 'code' ディレクトリが見つかりません。現在のディレクトリ: $(pwd)"
        read -p "Enterを押して終了します..."
        exit 1
    fi

    # ワイルドカードでファイルが無い場合にエラーになるのを防ぐ
    shopt -s nullglob

    # codeフォルダ内のファイルから動的にメニューを生成
    for file in code/*.py; do
        COUNT=$((COUNT + 1))
        filename=$(basename "$file")
        FILE_LIST[$COUNT]="$filename"

        # ファイルからタイトルを抽出 (# MENU_TITLE: を探す)
        raw_line=$(grep -m 1 "^# MENU_TITLE:" "$file" 2>/dev/null)
        
        if [ -n "$raw_line" ]; then
            # ':' で分割し、2つ目以降の要素を取得。その後、先頭の空白を削除
            temp_title=$(echo "$raw_line" | cut -d ':' -f 2- | sed -e 's/^[[:space:]]*//')
            if [ -n "$temp_title" ]; then
                TITLE_LIST[$COUNT]="$temp_title"
            else
                TITLE_LIST[$COUNT]="タイトルなし"
            fi
        else
            TITLE_LIST[$COUNT]="タイトルなし"
        fi

        echo "  [$COUNT] ${TITLE_LIST[$COUNT]} ($filename)"
    done
    shopt -u nullglob

    echo ""
    echo "  [0] 終了"
    echo ""
    echo "======================================================"

    read -p "実行する番号を選んでください [0-$COUNT]: " CHOICE

    # 終了処理
    if [ "$CHOICE" = "0" ]; then
        echo "👋 終了します。"
        exit 0
    fi

    # 入力値のバリデーション (空、数値以外、範囲外を弾く)
    if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "$COUNT" ]; then
        echo ""
        echo "❌ 不正な入力です。もう一度入力してください。"
        sleep 2
        continue
    fi

    # 選択されたスクリプトを取得して実行
    TARGET_SCRIPT="${FILE_LIST[$CHOICE]}"

    echo ""
    echo "🚀 $TARGET_SCRIPT を開始します..."
    python3 "code/$TARGET_SCRIPT"

    echo ""
    echo "------------------------------------------------------"
    read -p "処理が完了しました。Enterを押してメニューに戻ります..."
done