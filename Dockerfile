# --- Stage 1: Builder ---
# AS builder でパッケージダウンロードのみ行う
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# リポジトリ追加に必要なツールをインストール
RUN apt-get update && apt-get install -y wget gnupg curl unzip

# Google Chrome の .deb パッケージをダウンロード
RUN wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 必要な全パッケージと依存関係をダウンロードのみ行う (Chrome関連を除外)
RUN apt-get update && apt-get install -y --download-only \
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
    # Python, その他ツール
    python3 python3-pip dos2unix pcmanfm jq


# --- Stage 2: Final Image ---
# 最終イメージをクリーンな状態から構築
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu 24.04 (PEP 668) 対策: グローバルな pip install を許可
ENV PIP_BREAK_SYSTEM_PACKAGES=1 

# 1. Builderからパッケージリスト、ダウンロード済パッケージをコピー
COPY --from=builder /var/lib/apt/lists/ /var/lib/apt/lists/
COPY --from=builder /var/cache/apt/archives/ /var/cache/apt/archives/

# 2. update不要でインストールを実行 (ローカルキャッシュからすべてインストールされる)
RUN apt-get install -y \
    xfce4 xrdp supervisor sudo xfce4-terminal \
    xkb-data language-pack-ja fonts-noto-cjk \
    ibus-mozc ibus-gtk3 dbus-x11 dconf-cli \
    python3 python3-pip python3-venv dos2unix pcmanfm jq \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# システムのロケールを日本語に設定
RUN locale-gen ja_JP.UTF-8
RUN update-locale LANG=ja_JP.UTF-8

# rootパスワード設定
RUN echo 'root:password' | chpasswd

# ibus-setupがGUIで実行できるようポリシーを調整
RUN apt-get update && apt-get install -y policykit-1-gnome \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Google Chrome のインストール ---
# builderステージでダウンロード済みの .deb をコピーしてインストール
COPY --from=builder /tmp/google-chrome.deb /tmp/google-chrome.deb
RUN apt-get update && \
    dpkg -i /tmp/google-chrome.deb || true && \
    apt-get install -y -f && \
    rm /tmp/google-chrome.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash dockeruser
RUN echo 'dockeruser:password' | chpasswd

# sudoグループとxrdpグループに追加
RUN usermod -aG sudo dockeruser
RUN usermod -aG xrdp dockeruser

# sudo実行時にパスワードを不要にする
RUN echo 'dockeruser ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

RUN mkdir /data
# -R オプションで、/data ディレクトリと「その中身」の権限をdockeruserに設定
RUN chown -R dockeruser:dockeruser /data

# /etc/environment ファイルに書き込むことで、全プロセスが環境変数を継承
RUN echo 'GTK_IM_MODULE=ibus' >> /etc/environment
RUN echo 'QT_IM_MODULE=ibus' >> /etc/environment
RUN echo 'XMODIFIERS=@im=ibus' >> /etc/environment

RUN mkdir -p /home/dockeruser/.config/autostart

# 1. 実行スクリプト本体の作成
RUN echo '#!/bin/sh' > /home/dockeruser/config_keyboard.sh && \
    echo 'sleep 3' >> /home/dockeruser/config_keyboard.sh && \
    echo 'xfconf-query -c keyboards -p /Default/Restore -n -t bool -s false' >> /home/dockeruser/config_keyboard.sh && \
    echo 'xfconf-query -c keyboards -p /Default/XkbModel -n -t string -s "pc105"' >> /home/dockeruser/config_keyboard.sh && \
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

# --- PythonパッケージとPlaywrightのインストール ---
# 1. 仮想環境(venv)の構築とパスの優先設定
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# dockeruserもこの環境を使えるように権限を付与
RUN chown -R dockeruser:dockeruser $VIRTUAL_ENV

# 2. requirements.txt をインストール (venv環境内へ)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt

# 3. PlaywrightのOS依存パッケージをroot権限でインストール
RUN playwright install-deps chromium

# 4. 一般ユーザー(dockeruser)に切り替えてブラウザ本体をインストール
USER dockeruser
WORKDIR /home/dockeruser
RUN playwright install chromium
RUN echo "source /opt/venv/bin/activate" >> /home/dockeruser/.bashrc

# Supervisorの設定をコピー (root権限に戻す)
USER root
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# デスクトップのショートカット群をコピー
RUN mkdir -p /home/dockeruser/Desktop && chown dockeruser:dockeruser /home/dockeruser/Desktop

COPY launch_terminal.desktop /home/dockeruser/Desktop/
COPY open_browser.desktop /home/dockeruser/Desktop/
COPY google_chrome.desktop /home/dockeruser/Desktop/

RUN chmod +x /home/dockeruser/Desktop/*.desktop && \
    chown dockeruser:dockeruser /home/dockeruser/Desktop/*.desktop

# ポートを開放
EXPOSE 3389

# コンテナ起動時にSupervisorを実行
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]