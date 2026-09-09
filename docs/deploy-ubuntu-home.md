# Домашний сервер: Ubuntu 24.04, Mihomo, zapret2 и qBittorrent

Гайд для текущего проекта. Все команды выполняются на сервере в Bash, кроме явно отмеченных команд на Mac. Примеры используют пользователя `deploy` и адрес `SERVER_IP`: замени их своими. Сам сервер в этой задаче не настраивался; работа VPN и стратегии DPI требует проверки на твоём подключении.

## 1. Что получится

| Компонент / запрос | Путь |
|---|---|
| Telegram в bot и worker | HTTP CONNECT внутри Docker → клиент Mihomo → VPN → Telegram |
| Сайт RuTracker | Тот же клиент Mihomo |
| YouTube в yt-dlp, внешние запросы potoken | Docker → zapret2 на Ubuntu → домашний провайдер |
| qBittorrent: пиры, DHT, трекеры, раздача | Docker → домашний провайдер, без VPN |
| Управление qBittorrent | worker → qbittorrent:8080 внутри Docker |
| PostgreSQL и Redis | Внутри Docker |

Mihomo здесь работает в режиме прикладного прокси, без TUN и изменения default route сервера. SOCKS5 через интернет не используется. zapret2 не меняет публичный IP и не исправляет антибот-проверки YouTube.

Используем **отдельный** `compose.home.yml`, не объединяем его с `docker-compose.yml`. В нём есть qBittorrent, локальный Mihomo-клиент и закрытый снаружи potoken. Для сети задано постоянное имя Linux-интерфейса `br-bot-home`.

В код уже добавлены `TELEGRAM_PROXY_URL` и `RUTRACKER_PROXY_URL`. qBittorrent игнорирует прокси из окружения. Для aiogram установлена зависимость `aiohttp-socks`, которая нужна ему и для HTTP-прокси. Не задавай глобальные `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` в `.env`: yt-dlp должен выходить напрямую.

## 2. Подготовка Ubuntu и Docker

Проверь систему, свободное место и интерфейс выхода:

```bash
lsb_release -ds
uname -m
df -h
ip -4 route show default
```

Системный Python 3.12 менять не нужно: Python 3.14 устанавливается в образе бота. Учти место одновременно под торренты и временные YouTube-файлы. Для больших загрузок лучше отдельный диск, смонтированный постоянно через `/etc/fstab`.

На чистой Ubuntu установи Docker из официального репозитория:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git rsync openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF_DOCKER
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF_DOCKER
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Перезайди по SSH, затем:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Если Docker уже установлен и обслуживает другие приложения, не удаляй его пакеты и не меняй backend firewall вслепую. Сверь существующую установку с [инструкцией Docker](https://docs.docker.com/engine/install/ubuntu/). Членство в группе `docker` даёт административные возможности на сервере.

## 3. Перенос проекта

В рабочей копии есть незакоммиченные изменения. Простое клонирование удалённого репозитория может их не перенести. Для первого запуска можно скопировать текущие исходники.

На сервере:

```bash
mkdir -p ~/bot-urodetc
```

На Mac, из каталога проекта:

```bash
rsync -av --exclude='.git' --exclude='.venv' --exclude='.env' \
  --exclude='secrets' --exclude='cookies.txt' --exclude='data' \
  --exclude='backups' --exclude='__pycache__' \
  ./ deploy@SERVER_IP:~/bot-urodetc/
```

Это перенос без удаления файлов на сервере. В дальнейшем лучше развёртывать конкретный коммит, содержащий все нужные изменения.

На сервере:

```bash
cd ~/bot-urodetc
umask 077
mkdir -p secrets backups
cp .env.example .env
cp deploy/mihomo.example.yaml secrets/mihomo.yaml
chmod 700 secrets backups
chmod 600 .env secrets/mihomo.yaml
id -u
id -g
openssl rand -hex 24
```

Сохрани сгенерированную строку как пароль PostgreSQL. Используй именно hex-строку: она безопасно подставляется в URL подключения без дополнительного URL-кодирования.

## 4. Настройки .env и диска

```bash
nano .env
```

Заполни или добавь значения, не оставляя дублирующихся ключей:

```dotenv
BOT_TOKEN=реальный_токен_бота
OWNER_TELEGRAM_IDS=твой_числовой_telegram_id
LOG_LEVEL=INFO
POSTGRES_PASSWORD=сгенерированная_hex_строка
PUID=1000
PGID=1000
TORRENT_DIR=/srv/torrents

RUTRACKER_URL=https://rutracker.org
RUTRACKER_USERNAME=логин
RUTRACKER_PASSWORD='пароль'
RUTRACKER_SESSION=

QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD='пароль_который_задашь_в_WebUI'
QBITTORRENT_CATEGORY=cinema

COOKIES_FILE=
```

PUID/PGID возьми из `id -u` и `id -g`. Одинарные кавычки в dotenv удобны для паролей с `$` и `#`; если сам пароль содержит кавычки, учитывай правила dotenv. Не используй `. .env` или `source .env`: это файл Compose, не shell-скрипт.

`compose.home.yml` сам устанавливает URL PostgreSQL, Redis, прокси, qBittorrent, potoken и путь скачивания. `LOCAL_API_BASE` в этом варианте пустой. Для управления VPN заполни REMNAWAVE-поля отдельно; если оно не нужно, удали демонстрационные значения URL, токена и UUID из `.env`.

Создай каталог торрентов. Ниже 1000:1000 замени на выбранные PUID:PGID:

```bash
sudo install -d -o 1000 -g 1000 /srv/torrents /srv/torrents/cinema
```

Если диск смонтирован в другом месте, укажи его каталог в `TORRENT_DIR`. В qBittorrent он всё равно виден как `/downloads`, а путь назначения бота — `/downloads/cinema`.

## 5. Mihomo

Нужен **URL подписки пользователя Remnawave**. Это не API-токен панели и не отдельная ссылка `vless://` / `hy2://`. Скопируй подписку из панели и открой конфиг:

```bash
nano secrets/mihomo.yaml
```

В `proxy-providers.remnawave.url` замени демонстрационный URL своим. Остальной файл оставь из `deploy/mihomo.example.yaml`. Переменные `.env` внутри этого YAML автоматически не подставляются.

Используется образ `metacubex/mihomo:latest`. Конфигурация загружает узлы через HTTP provider каждый час и хранит кеш в volume `mihomodata`. Группа `VPN` типа `fallback` выбирает первый доступный узел по результатам проверки. Добавленного нами выхода `DIRECT` в этой группе нет; через прокси должны идти все запросы, которые приложения направили на `http://mihomo:8080`. Успех проверки доступности узла не гарантирует доступность Telegram — проверь его отдельно ниже.

Заголовок `User-Agent: mihomo` запрашивает формат Mihomo у Remnawave. В ответ нужен YAML с непустым списком `proxies`. HTML-страница, JSON для другого клиента или шаблон, состоящий только из вложенных providers, для этой схемы не подходят. При необходимости настрой выдачу формата в панели. Загружаются узлы, а правила маршрутизации и группы из полного удалённого профиля не импортируются: используются локальные правила этого проекта. Если профиль использует сложные цепочки, их зависимости потребуется перенести отдельно.

Подписка при первом запуске загружается напрямую. Её домен должен быть доступен с сервера без ещё не настроенного VPN. Если он заблокирован, сначала обеспечь доступ к домену; загрузка через собственную пока пустую группу `VPN` создаст замкнутую зависимость. При HWID-привязке соблюди требования своей панели для отдельного устройства, иначе она может вернуть пустую подписку.

Порт прокси не опубликован на хост, API управления не включён, TUN и NET_ADMIN не нужны. TLS-проверку узлов не отключай. URL подписки и кеш содержат доступ к VPN: не публикуй их, сохрани права 600 на конфиг.

Документация: [HTTP providers Mihomo](https://wiki.metacubex.one/en/config/proxy-providers/), [форматы подписок Remnawave](https://docs.rw/learn-en/templates/).

```bash
docker compose -f compose.home.yml config --quiet
docker compose -f compose.home.yml pull
docker compose -f compose.home.yml build
docker compose -f compose.home.yml up -d mihomo db redis potoken qbittorrent
docker compose -f compose.home.yml logs --tail=50 mihomo
```

Не отправляй сырые логи Mihomo другим людям: в них может оказаться URI доступа. Успешный запуск контейнера ещё не проверяет туннель.

Сравни прямой и проксированный выход из образа worker:

```bash
docker compose -f compose.home.yml run --rm --no-deps worker \
  curl -4 --noproxy '*' --max-time 20 https://api.ipify.org

docker compose -f compose.home.yml run --rm --no-deps worker \
  curl --proxy http://mihomo:8080 --max-time 20 https://api.ipify.org
```

В первом случае ожидается домашний публичный IPv4, во втором — выход VPN. Если сервис проверки IP недоступен, это ещё не доказательство поломки туннеля: проверь целевой сервис.

Проверка Telegram через **тот же код**, который используют bot и worker, без вывода токена:

```bash
docker compose -f compose.home.yml run --rm -T --no-deps worker python - <<'PY'
import asyncio
from app.infrastructure.config import Settings
from app.telegram.bot import build_bot
async def main():
    bot = build_bot(Settings.from_env())
    try:
        me = await bot.get_me()
        print('Telegram OK:', me.username)
    finally:
        await bot.session.close()
asyncio.run(main())
PY
```

Проверка доступности сайта RuTracker, пока без авторизации:

```bash
docker compose -f compose.home.yml run --rm --no-deps worker \
  curl --proxy http://mihomo:8080 --max-time 30 -L -o /dev/null \
  -w '%{http_code}\n' https://rutracker.org/forum/index.php
```

Таймаут Mihomo означает, что сначала надо проверить загрузку подписки, наличие узлов и доступность выбранного транспорта. Наличие подписки само по себе не доказывает, что её транспорт работает из этой сети.

### Переход с прежнего Hysteria-контейнера

После переноса новых файлов создай `secrets/mihomo.yaml` по шаблону выше. Если старый стек уже работает, сначала подними Mihomo и проверь Telegram командой из этого раздела. Затем пересоздай приложения и удали только старый контейнер:

```bash
docker compose -f compose.home.yml up -d mihomo
docker compose -f compose.home.yml up -d bot worker
docker ps -a --filter label=com.docker.compose.project=bot-home --filter label=com.docker.compose.service=hysteria --format '{{.ID}} {{.Names}}'
```

Если список содержит старый Hysteria этого проекта, удали его командой `docker rm -f ИД_ИЗ_СПИСКА`. Не применяй `down -v`. Старый `secrets/hysteria.yaml` после успешного перехода больше не используется.

После редактирования URL или локальных правил выполни `docker compose -f compose.home.yml restart mihomo`. Для проверки синтаксиса с заполненным конфигом: `docker compose -f compose.home.yml run --rm --no-deps mihomo -t -d /root/.config/mihomo -f /etc/mihomo/config.yaml`. Это не заменяет проверку загрузки подписки и запросов через прокси.

## 6. qBittorrent

```bash
docker compose -f compose.home.yml logs --tail=100 qbittorrent
```

В свежей установке найди временный пароль администратора в логах. Открой отдельный терминал на Mac:

```bash
ssh -N -L 18080:127.0.0.1:8080 deploy@SERVER_IP
```

Пока команда работает, открой `http://127.0.0.1:18080` в браузере. WebUI опубликован только на loopback сервера. Настройки образа и временный пароль описаны у [LinuxServer](https://docs.linuxserver.io/images/docker-qbittorrent/).

В qBittorrent:

1. Задай постоянный логин/пароль WebUI и перенеси их в `.env`.
2. Оставь авторизацию включённой, включая локальные подключения.
3. Установи путь загрузки `/downloads/cinema` или создай категорию `cinema` с этим путём.
4. Proxy Server: **None**. Network interface: обычный доступный интерфейс контейнера, без VPN.
5. Порт входящих соединений — **6881**, случайный порт при старте выключен.
6. При желании ограничь скорость раздачи, чтобы не занимать весь домашний uplink.

Не отключай CSRF/Host Header protection заранее. При ошибке Host header добавь используемое имя в разрешённые домены WebUI (внутренний клиент обращается к `qbittorrent`), сохрани защиту и повтори проверку.

Проброс 6881 TCP/UDP на роутере нужен для входящих пиров и доступен при подходящем публичном адресе. За CGNAT входящих соединений может не быть, но исходящие загрузки обычно возможны. Не пробрасывай WebUI, PostgreSQL, Redis и potoken. Docker-публикация портов имеет собственные правила firewall — не полагайся только на UFW.

## 7. zapret2 на Ubuntu

Этот этап зависит от провайдера. Не копируй параметры `--dpi-desync` из zapret1 в zapret2: здесь стратегии используют Lua. Исходники и назначение инструмента: [zapret2](https://github.com/bol-van/zapret2).

Для новой установки, если `/opt/zapret2` ещё не занят:

```bash
sudo git clone --recursive https://github.com/bol-van/zapret2.git /opt/zapret2
cd /opt/zapret2
sudo ./install_prereq.sh
sudo ./install_bin.sh
sudo ./blockcheck2.sh
```

Если установщик сообщает об отсутствии бинарников, используй полный release для Linux либо сборку по инструкции проекта; не продолжай с неработающим `nfqws2`. Запиши установленный коммит командой `git rev-parse HEAD`.

В blockcheck выбери `www.youtube.com`, сначала IPv4 и HTTPS/TCP. Запиши успешную стратегию. Проверка главной страницы не гарантирует доступ к CDN. Если запущен другой DPI-сервис, останови его на время теста, чтобы результаты не смешивались.

Установи сервис интерактивным установщиком:

```bash
sudo ./install_easy.sh
sudo nano /opt/zapret2/config
```

Выбери nftables, включи nfqws2, режим **hostlist** и HTTPS/TCP 443. Для первого запуска yt-dlp достаточно проверки TCP; обработку UDP/QUIC не включай без необходимости. В `NFQWS2_OPT` перенеси успешную стратегию blockcheck, сохранив фильтрацию TLS и маркер `<HOSTLIST>` в соответствующем профиле. **Вывод blockcheck не является готовым файлом config**: не заменяй им весь конфиг.

Ориентиры для редактирования текущего config (это не полный конфиг, параметры стратегии остаются твоими):

```bash
FWTYPE=nftables
NFQWS2_ENABLE=1
NFQWS2_PORTS_TCP=443
NFQWS2_PORTS_UDP=
MODE_FILTER=hostlist
IFACE_LAN=br-bot-home
IFACE_WAN=eno1
```

`eno1` обязательно замени на интерфейс из `ip -4 route show default`. Не копируй его буквально, если у тебя `enp…`, bond или VLAN. Не включай `POSTNAT=0` без причины: post-NAT режим полезен для транзитного Docker-трафика. Конкретные имена параметров сверены с [config.default](https://github.com/bol-van/zapret2/blob/master/config.default).

Добавь начальный список доменов, сохранив существующие записи, если список уже был:

```bash
sudo touch /opt/zapret2/ipset/zapret-hosts-user.txt
sudo nano /opt/zapret2/ipset/zapret-hosts-user.txt
```

```text
youtube.com
youtu.be
googlevideo.com
ytimg.com
youtubei.googleapis.com
```

Это начальный список, не исчерпывающая гарантия. Уточняй его по фактическим неуспешным обращениям. Не включай весь `google.com` без необходимости. Если DNS возвращает подменённые адреса, сначала исправь разрешение имён; обработка TLS не исправляет DNS-подмену.

```bash
sudo systemctl restart zapret2
sudo systemctl enable zapret2
sudo systemctl status zapret2 --no-pager
sudo journalctl -u zapret2 -n 80 --no-pager
sudo nft list ruleset
```

Убедись, что правила охватывают трафик с `br-bot-home`, а не только OUTPUT хоста. После изменения настроек перепроверь Telegram через Mihomo. Не выполняй `nft flush ruleset` или `iptables -F`: это уничтожит в том числе Docker-правила.

Для первоначального воспроизведения используй IPv4. Если включаешь IPv6 для контейнеров, его маршрут и правила нужно проверить отдельно. Работоспособность IPv4 ничего не говорит о IPv6.

## 8. Проверка YouTube из контейнера

Вернись в проект:

```bash
cd ~/bot-urodetc
docker compose -f compose.home.yml run --rm --no-deps worker \
  curl -4 --noproxy '*' --max-time 20 -I https://www.youtube.com
```

Проверь загрузку короткого доступного ролика, который вправе скачивать, через настройки провайдера проекта. Команда спросит URL, скачает один файл в `/tmp` временного контейнера и удалит его вместе с контейнером:

```bash
read -r -p 'YouTube URL: ' TEST_VIDEO_URL
docker compose -f compose.home.yml run --rm --no-deps \
  -e TEST_VIDEO_URL="$TEST_VIDEO_URL" worker python -c '
import os
import yt_dlp
from app.infrastructure.config import Settings
from app.tools.video.provider import YtDlpProvider
opts = YtDlpProvider(Settings.from_env())._base_opts()
opts.update({"quiet": False, "no_warnings": False, "proxy": "", "source_address": "0.0.0.0", "format": "worst[ext=mp4]/worst", "outtmpl": "/tmp/youtube-test.%(ext)s"})
with yt_dlp.YoutubeDL(opts) as ydl:
    ydl.download([os.environ["TEST_VIDEO_URL"]])
'
```

`_base_opts()` здесь используется только как диагностический помощник, чтобы проверить установленный плагин и параметры проекта. Затем обязательно проверь обычную команду бота: эта проверка принудительно использует IPv4 и низкое качество.

Различай ошибки:

- Таймаут или reset — проверяй DNS, CDN, правила Docker/zapret2 и стратегию.
- `Sign in to confirm…`, 403, PO token — проверяй yt-dlp, potoken и требования конкретного видео.
- Страница открывается, файл не качается — проверяй `googlevideo.com` и фактический CDN.
- Нет JS runtime / challenge solver — выполни актуальные требования [yt-dlp EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS); текущий Dockerfile не устанавливает отдельный JS runtime. Не путай это с сетевой блокировкой.

PO-токены не заменяют обход DPI. Актуальные требования: [руководство PO Token](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide).

Cookies добавляй только при необходимости. Скопируй Netscape cookies в `secrets/youtube-cookies.txt`, выставь `chmod 600` и задай:

```dotenv
COOKIES_FILE=/run/bot-secrets/youtube-cookies.txt
```

Каталог уже смонтирован в bot и worker. Cookies, `.env` и VPN-профиль исключены из сборочного контекста. Для экспорта используй [инструкцию yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies); cookies дают доступ к аккаунту, не публикуй их.

## 9. Запуск и приёмка

Останови другую polling-копию этого же бота на Mac или другом сервере. Два polling-процесса с одним токеном будут конфликтовать. worker — отдельный процесс, это нормально.

```bash
docker compose -f compose.home.yml config --quiet
docker compose -f compose.home.yml up -d
docker compose -f compose.home.yml ps
docker compose -f compose.home.yml logs --tail=100 bot worker
```

В Telegram проверь последовательно:

1. `/menu` — бот получает сообщения и отвечает.
2. `/download ССЫЛКА` — скачивает небольшой ролик и отправляет его.
3. `/cinema` — запусти поиск через интерфейс.
4. Добавь выбранную раздачу и проверь, что она появилась в qBittorrent в `/downloads/cinema`.
5. `/cinema_status` — проверь обновление статуса.

Если RuTracker требует CAPTCHA, возьми `bb_session` из авторизованного браузера, задай `RUTRACKER_SESSION` и пересоздай worker. Сессия может истечь.

Здесь используется облачный Telegram Bot API и текущий лимит проекта 50 MB. Для больших файлов нужен отдельный Local Bot API Server и правильные пути общих файлов; он сам тоже должен иметь доступ к Telegram. Этот гайд его не включает. Не повышай только `MAX_FILE_SIZE_MB`: серверный лимит от этого не изменится.

Проверка независимости торрентов: запусти разрешённую тестовую раздачу, затем временно останови Mihomo:

```bash
docker compose -f compose.home.yml stop mihomo
```

Telegram и поиск RuTracker должны перестать работать через этот прокси, а qBittorrent — продолжить обмен с доступными пирами. Сразу восстанови:

```bash
docker compose -f compose.home.yml up -d mihomo
```

Заблокированный адрес torrent-трекера при прямом подключении может оставаться недоступным. DHT не заменяет трекер для всех раздач, особенно private. Это отдельное ограничение требования «весь torrent напрямую».

## 10. Перезагрузка, обновление, резервные копии

После успешной приёмки перезагрузи сервер и повтори `/menu`, скачивание и проверку qBittorrent:

```bash
sudo reboot
```

Контейнеры используют `restart: unless-stopped`, Docker и zapret2 включены в systemd. Проверь после загрузки `docker compose -f compose.home.yml ps` и `systemctl status zapret2`. Если правила зависели от ещё не созданного bridge, перезапусти zapret2 и настрой порядок запуска по результатам проверки, не считай автозапуск проверенным заранее.

Обновление исходников: перенеси новую версию, затем:

```bash
cd ~/bot-urodetc
docker compose -f compose.home.yml build
docker compose -f compose.home.yml up -d
```

После изменения `.env` также нужен `up -d`, одного `restart` недостаточно. Образы с `latest` не обновляются сами: для обновления нужен `pull`. После рабочего запуска сохрани используемые digests (`docker image inspect IMAGE --format '{{json .RepoDigests}}'`) и зафиксируй их в Compose, чтобы следующее развёртывание не принесло неожиданные версии.

Резервная копия базы перед обновлением:

```bash
umask 077
mkdir -p backups
docker compose -f compose.home.yml exec -T db pg_dump -U bot -d bot -Fc > "backups/bot-$(date +%F-%H%M%S).dump"
```

Проверка структуры дампа:

```bash
docker compose -f compose.home.yml exec -T db pg_restore --list < backups/ИМЯ_ФАЙЛА.dump
```

Также сохраняй `.env`, `secrets`, `/opt/zapret2/config`, hostlist, `/srv/torrents` и volume конфигурации qBittorrent. Для согласованной копии qBittorrent останови его на время резервирования volume. Храни резервную копию на другом носителе; список содержимого дампа не заменяет пробное восстановление.

Восстановление БД **заменяет текущие данные**. Для сознательного отката:

```bash
docker compose -f compose.home.yml stop bot worker
docker compose -f compose.home.yml exec -T db pg_restore -U bot -d bot \
  --clean --if-exists --no-owner < backups/ИМЯ_ФАЙЛА.dump
docker compose -f compose.home.yml up -d bot worker
```

Не меняй `POSTGRES_PASSWORD` в `.env` после инициализации volume без изменения пароля роли в самой БД. Не используй `down -v` для обычного обновления: оно удаляет именованные volumes, включая БД и настройки qBittorrent.

## 11. Быстрая диагностика

| Симптом | Что проверять |
|---|---|
| Telegram Conflict | Другую polling-копию, старый webhook |
| Telegram timeout | Mihomo, загрузку подписки, наличие и доступность узлов |
| RuTracker работает в curl, поиск нет | Авторизацию, CAPTCHA, срок сессии |
| qBittorrent 401/403 | Постоянный пароль, бан после неудачных входов, Host header |
| YouTube на Ubuntu работает, в worker нет | `br-bot-home`, transit/postrouting, IPv4/IPv6 и DNS контейнера |
| YouTube 403 / bot challenge | Версии yt-dlp, PO-токены, cookies, JS runtime |
| Торрент стоит | Пиры, доступность трекера, место, права каталога, CGNAT |
| PostgreSQL authentication failed | Пароль существующего volume не совпадает с `.env` |
| После ребута сеть сломалась | Правила Docker, порядок запуска zapret2, внешний диск |

Логи смотри адресно: `docker compose -f compose.home.yml logs --tail=100 worker` или `sudo journalctl -u zapret2 -n 100`. Перед передачей логов удали токены, профили, cookies и приватные URL. Не отправляй полный вывод `docker compose config`: он раскрывает подставленные секреты, используй `config --quiet`.
