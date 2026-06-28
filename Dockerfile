# --- Stage 1: Builder ---
# AS builder でリポジトリ追加とパッケージダウンロードのみ行う
FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# 1. リポジトリ追加に必要なツールをインストール
# (この時点ではUbuntuのデフォルトリストのみを使う)
RUN apt-get update && apt-get install -y wget gnupg

# 2. Google Chromeのリポジトリを追加
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

RUN apt-get update

# 4. 必要な全パッケージと依存関係をダウンロードのみ行う
RUN apt-get install -y --download-only \
    # デスクトップ環境とRDP
    xfce4 xrdp supervisor sudo \
    # キーボード/ロケール関連
    xkb-data \
    language-pack-ja \
    fonts-noto-cjk \
    # IBus/Mozc 関連
    ibus-mozc \
    ibus-gtk3 \
    dbus-x11 \
    # dconf
    dconf-cli \
    # Python, Chrome, その他ツール
    python3 python3-pip wget gnupg unzip dos2unix pcmanfm jq \
    google-chrome-stable


# --- Stage 2: Final Image ---
# 最終イメージをクリーンな状態から構築
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 1. Builderからリポジトリ設定、パッケージリスト、ダウンロード済パッケージをコピー
COPY --from=builder /etc/apt/sources.list.d/google-chrome.list /etc/apt/sources.list.d/google-chrome.list
COPY --from=builder /usr/share/keyrings/google-chrome-keyring.gpg /usr/share/keyrings/google-chrome-keyring.gpg
COPY --from=builder /var/lib/apt/lists/ /var/lib/apt/lists/
COPY --from=builder /var/cache/apt/archives/ /var/cache/apt/archives/

# 2. update不要でインストールを実行 (ローカルキャッシュからすべてインストールされる)
RUN apt-get install -y \
    # デスクトップ環境とRDP
    xfce4 xrdp supervisor sudo \
    # キーボード/ロケール関連
    xkb-data \
    language-pack-ja \
    fonts-noto-cjk \
    # IBus/Mozc 関連
    ibus-mozc \
    ibus-gtk3 \
    dbus-x11 \
    # dconf
    dconf-cli \
    # Python, Chrome, その他ツール
    python3 python3-pip wget gnupg unzip dos2unix pcmanfm jq \
    google-chrome-stable \
    # 最終的なイメージからaptキャッシュを削除
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# システムのロケールを日本語に設定
RUN locale-gen ja_JP.UTF-8
RUN update-locale LANG=ja_JP.UTF-8

# rootパスワード設定
RUN echo 'root:password' | chpasswd

# ibus-setupがGUIで実行できるようポリシーを調整
# (Ubuntu 22.04で一般ユーザーがibus-setupを実行するのに必要)
RUN apt-get update && apt-get install -y policykit-1-gnome \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash dockeruser
RUN echo 'dockeruser:password' | chpasswd

# sudoグループとxrdpグループに追加
RUN usermod -aG sudo dockeruser
RUN usermod -aG xrdp dockeruser

# sudo実行時にパスワードを不要にする (任意だが推奨)
RUN echo 'dockeruser ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

RUN mkdir /data
# -R オプションで、/data ディレクトリと「その中身」の権限をdockeruserに設定
RUN chown -R dockeruser:dockeruser /data

# /etc/environment ファイルに書き込むことで、全プロセスが環境変数を継承します
RUN echo 'GTK_IM_MODULE=ibus' >> /etc/environment
RUN echo 'QT_IM_MODULE=ibus' >> /etc/environment
RUN echo 'XMODIFIERS=@im=ibus' >> /etc/environment

RUN mkdir -p /home/dockeruser/.config/autostart

# 1. 実行スクリプト本体の作成
RUN echo '#!/bin/sh' > /home/dockeruser/config_keyboard.sh && \
    # デスクトップが完全に起動するまで3秒待つ
    echo 'sleep 3' >> /home/dockeruser/config_keyboard.sh && \
    # 「システムデフォルトを使用する」をオフ
    echo 'xfconf-query -c keyboards -p /Default/Restore -n -t bool -s false' >> /home/dockeruser/config_keyboard.sh && \
    # モデルを 105キーに設定
    echo 'xfconf-query -c keyboards -p /Default/XkbModel -n -t string -s "pc105"' >> /home/dockeruser/config_keyboard.sh && \
    # レイアウトを日本語(jp)に設定
    echo 'xfconf-query -c keyboards -p /Default/XkbLayout -n -t string -s "jp"' >> /home/dockeruser/config_keyboard.sh && \
    chmod +x /home/dockeruser/config_keyboard.sh

# 2. XFCEが自動起動で読み込むための .desktop ファイルを作成
RUN echo '[Desktop Entry]' > /home/dockeruser/.config/autostart/keyboard.desktop && \
    echo 'Name=Keyboard Fix' >> /home/dockeruser/.config/autostart/keyboard.desktop && \
    echo 'Exec=/home/dockeruser/config_keyboard.sh' >> /home/dockeruser/.config/autostart/keyboard.desktop && \
    echo 'Type=Application' >> /home/dockeruser/.config/autostart/keyboard.desktop

# 3. 権限を dockeruser に設定
RUN chown -R dockeruser:dockeruser /home/dockeruser/config_keyboard.sh
RUN chown -R dockeruser:dockeruser /home/dockeruser/.config

# IBusの入力メソッドをMozcに設定 (システム全体)
RUN mkdir -p /etc/dconf/db/ibus.d && \
    echo '[org/freedesktop/ibus/general]\npreload-engines=["mozc-jp"]' > /etc/dconf/db/ibus.d/00-mozc-settings && \
    dconf update

# startwm.sh をコピーし、改行コードを修正
COPY startwm.sh /etc/xrdp/startwm.sh
RUN dos2unix /etc/xrdp/startwm.sh
RUN chmod +x /etc/xrdp/startwm.sh

# ChromeDriverをインストール
RUN CHROME_VERSION=$(google-chrome --version | cut -d " " -f3 | cut -d "." -f1,2,3) \
    && DRIVER_VERSION=$(wget -q -O - "https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build.json" | jq -r ".builds[\"${CHROME_VERSION}\"].version") \
    && wget -O /tmp/chromedriver.zip "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip

# Seleniumライブラリをインストール
RUN pip3 install selenium requests

# Supervisorの設定
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# デスクトップアイコン
COPY launch_chrome.desktop /home/dockeruser/Desktop/
RUN chmod +x /home/dockeruser/Desktop/launch_chrome.desktop && \
    chown dockeruser:dockeruser /home/dockeruser/Desktop/launch_chrome.desktop

# ポートを開放
EXPOSE 3389 9222

# コンテナ起動時にSupervisorを実行
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]