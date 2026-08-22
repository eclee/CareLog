# CareLog 1.2.0 建置、部署與維運手冊

## 1. 適用範圍

本手冊涵蓋：

- Python 虛擬環境；
- Docker Compose；
- Linux／NAS 的 Waitress＋systemd；
- HTTPS 或私人網路；
- SQLite、設定及照片備份；
- 資料庫升級、媒體搬移與異常重建；
- 基本故障檢查。

CareLog 預設以單一家庭、低併發與受控網路為前提。公開網路部署前，務必採用 HTTPS、強密碼、隨機 session 金鑰與定期備份。

## 2. 環境變數

| 變數 | 預設 | 說明 |
|---|---:|---|
| `CARELOG_SECRET` | 不安全的示範值 | Flask session 簽章金鑰；正式環境必改 |
| `CARELOG_DATA` | 專案目錄 | `carelog.db` 與 `uploads/` 的父目錄 |
| `CARELOG_PORT` | `8500` | `python app.py` 使用的埠 |
| `CARELOG_START_SCHEDULER` | `1` | 是否啟動排程器；CLI／測試設為 `0` |
| `CARELOG_CSRF_ENABLED` | `1` | CSRF 防護；正式環境不得關閉 |
| `CARELOG_HOST_PORT` | `8501` | Docker Compose 對外映射的主機埠 |
| `WAITRESS_THREADS` | `4` | Docker Waitress 執行緒數 |
| `SEED_DEMO` | `0` | Docker 啟動時是否建立示範資料 |
| `TZ` | `Asia/Taipei` | 報表、提醒與飲水結算的主機時區 |

產生 session 金鑰：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 3. Python 虛擬環境

```bash
git clone <YOUR_REPOSITORY_URL>
cd CareLog-1.2.0
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

export CARELOG_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
CARELOG_START_SCHEDULER=0 flask --app app init-db
python app.py
```

啟動後開啟：

```text
http://127.0.0.1:8500
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:CARELOG_SECRET = python -c "import secrets; print(secrets.token_hex(32))"
$env:CARELOG_START_SCHEDULER = "0"
flask --app app init-db
$env:CARELOG_START_SCHEDULER = "1"
python app.py
```

### 使用 uv

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
CARELOG_START_SCHEDULER=0 uv run flask --app app init-db
uv run python app.py
```

## 4. Docker Compose

```bash
cp .env.example .env
# 編輯 .env，填入隨機 CARELOG_SECRET
docker compose up -d --build
docker compose logs -f carelog
```

資料位置：

```text
data/carelog.db
data/uploads/
```

Docker entrypoint 每次啟動會以停用排程器的模式執行 `init-db`，建立缺少的表並套用可重複的相容性升級，接著才啟動 Waitress。

停止與啟動：

```bash
docker compose stop
docker compose start
```

更新程式：

```bash
docker compose stop
cp -a data "data-backup-$(date +%Y%m%d-%H%M%S)"
git pull --ff-only
docker compose up -d --build
```

## 5. Waitress＋systemd

建立專用帳號與目錄：

```bash
sudo useradd --system --home /opt/carelog --shell /usr/sbin/nologin carelog
sudo mkdir -p /opt/carelog /var/lib/carelog
sudo chown -R carelog:carelog /opt/carelog /var/lib/carelog
```

以 `carelog` 使用者建立虛擬環境、安裝套件並執行：

```bash
CARELOG_DATA=/var/lib/carelog CARELOG_START_SCHEDULER=0 \
  /opt/carelog/.venv/bin/flask --app app init-db
```

建立 `/etc/systemd/system/carelog.service`：

```ini
[Unit]
Description=CareLog home-care reporting platform
After=network.target

[Service]
Type=simple
User=carelog
Group=carelog
WorkingDirectory=/opt/carelog
Environment=CARELOG_DATA=/var/lib/carelog
Environment=CARELOG_SECRET=<RANDOM_SECRET>
Environment=CARELOG_START_SCHEDULER=1
Environment=CARELOG_CSRF_ENABLED=1
Environment=TZ=Asia/Taipei
ExecStart=/opt/carelog/.venv/bin/waitress-serve --host=127.0.0.1 --port=8500 --threads=4 --call app:create_app
Restart=always
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now carelog
sudo systemctl status carelog
journalctl -u carelog -f
```

Waitress 建議只監聽 `127.0.0.1`，再由反向代理提供 HTTPS。

## 6. 反向代理與私人網路

建議二擇一：

1. **Tailscale／WireGuard**：只有家庭成員裝置能連線；
2. **反向代理＋HTTPS**：Nginx、Caddy 或 NAS 反向代理將 HTTPS 轉送到 `127.0.0.1:8500`。

不要直接把 Flask 開發伺服器或未加密的 Waitress 埠暴露到 Internet。

## 7. Gmail、異常與排程

排程器必須只啟動一次。正式服務設 `CARELOG_START_SCHEDULER=1`；初始化、升級、測試與資料搬移設為 `0`。

排程工作包括：

- 每日／每週／最近 30 日報表；
- 餐飲未填提醒；
- 啟用時的每日飲水不足結算。

生命徵象異常由請求流程立即判定並保存，接著才嘗試寄信。SMTP 失敗時，後台異常事件仍存在並保存通知狀態。

Gmail 請使用 Google 應用程式密碼。寄信失敗時檢查：

- SMTP 帳號與應用程式密碼；
- 收件人格式；
- 主機能否連線到 Gmail SMTP；
- 主機／容器時區；
- CareLog 應用程式日誌。

## 8. 結構化圖片與容量

圖片保存於 `CARELOG_DATA/uploads/`，新資料依長輩、日期、紀錄類型與紀錄 ID 分層。每張圖片會產生原圖 JPEG 與縮圖，因此估算儲存容量時應計入兩份檔案。

後台參數可調整：

- 每筆照顧填報最多圖片；
- 每項用藥計畫最多參考圖片。

Flask 單次請求預設上限為 32 MB，單一圖片由媒體服務限制為 20 MB。這些屬部署安全限制，不提供後台網頁修改。

## 9. 備份與還原

### 備份

先停止服務，再複製整個資料目錄：

```bash
docker compose stop
cp -a data "data-backup-$(date +%Y%m%d-%H%M%S)"
docker compose start
```

systemd：

```bash
sudo systemctl stop carelog
sudo cp -a /var/lib/carelog "/var/backups/carelog-$(date +%Y%m%d-%H%M%S)"
sudo systemctl start carelog
```

備份應包含資料庫與全部圖片，不能只備份其中一者，否則資料列與實體檔案可能失去對應。

### 還原

1. 停止 CareLog；
2. 將備份的 `carelog.db` 與 `uploads/` 放回同一資料目錄；
3. 確認檔案擁有者與權限；
4. 啟動服務；
5. 依長輩、照片、操作紀錄與異常事件抽樣檢查。

## 10. 從 1.1.0 升級

完整流程請見 [UPGRADE.md](UPGRADE.md)。核心命令：

```bash
CARELOG_START_SCHEDULER=0 flask --app app upgrade-db
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --dry-run
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --apply
```

選用的歷史異常重建：

```bash
CARELOG_START_SCHEDULER=0 flask --app app rebuild-abnormal-events \
  --from-date 2026-01-01 --to-date 2026-08-22
```

## 11. 常用維護命令

```bash
make upgrade
make media-preview
make media-migrate
make rebuild-abnormal
make check
```

直接使用 Flask CLI：

```bash
CARELOG_START_SCHEDULER=0 flask --app app routes
CARELOG_START_SCHEDULER=0 flask --app app upgrade-db
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --dry-run
```

## 12. 故障檢查

### 程式與模板

```bash
python -m compileall -q .
python scripts/check_translations.py
python scripts/static_check.py
python -m pytest
```

### Docker

```bash
docker compose ps
docker compose logs --tail=200 carelog
docker compose exec -e CARELOG_START_SCHEDULER=0 carelog flask --app app routes
```

### 圖片

- 後台照片庫查得到但顯示 404：檢查資料庫路徑與 `uploads/` 實體檔案；
- 舊照片仍在舊目錄：先執行 `media-migrate --dry-run`；
- 圖片上傳失敗：檢查檔案是否為真實圖片、大小、資料目錄權限及應用程式日誌；
- 縮圖不存在時，媒體路由會暫時回退到原圖，但應修復或重新搬移該筆圖片。

### 異常事件

- 有超標數值但沒有事件：確認「參數設定」中的規則已啟用；
- 有事件但沒有 Email：查看事件的 `notification_status` 並檢查 SMTP；
- 飲水不足沒有產生：確認長輩喝水目標、規則開關、結算時間及排程器時區。
