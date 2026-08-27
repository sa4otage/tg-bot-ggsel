#!/bin/bash
# Ручной деплой на сервер: устанавливает зависимости и поднимает systemd-сервис.
# Секреты сюда НЕ зашиваются -- .env должен быть создан заранее в этой же
# папке (см. .env.example) и НЕ должен попадать в git.
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$APP_DIR/.env" ]; then
    echo "Не найден $APP_DIR/.env -- скопируй .env.example в .env и заполни значения перед запуском."
    exit 1
fi

pip3 install -r "$APP_DIR/requirements.txt" -q

cat > /etc/systemd/system/tgbot.service << SERVICEEOF
[Unit]
Description=Telegram Code Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 bot.py
EnvironmentFile=$APP_DIR/.env
Restart=always
RestartSec=5
# Даём процессу время закрыть сессию с Telegram корректно перед рестартом,
# иначе новый инстанс может словить TelegramConflictError от старого.
TimeoutStopSec=15
KillMode=mixed

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable tgbot
systemctl restart tgbot
sleep 3
systemctl status tgbot --no-pager | head -20
echo "=== БОТ ЗАПУЩЕН ==="
