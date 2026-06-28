#!/bin/sh
# RDPセッションのキーボードレイアウトを強制的に日本語(jp)に設定
# (これは低レベルのフォールバックとして残します)
setxkbmap jp

# DBusセッションを強制的に起動
eval $(dbus-launch --sh-syntax)

# IBusデーモン (このDBusセッション上で起動)
ibus-daemon -drx &

# Xfceデスクトップ環境を起動
startxfce4