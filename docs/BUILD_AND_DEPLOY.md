# CareLog 建置、部署與升級手冊

## 1. 適用範圍

本手冊涵蓋：

- Python 虛擬環境；
- Docker Compose；
- Linux／NAS 的 Waitress＋systemd；
- HTTPS 或 VPN；
- SQLite 與照片備份；
- 從 1.0 升級到 1.1。

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
| `TZ` | `Asia/Taipei` | 報表與提醒排程時區 |

產生 session 金鑰：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 3. Python 虛擬環境

```bash
git clone <YOUR_REPOSITORY_URL>
cd carelog
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

CARELOG_START_SCHEDULER=0 flask --app app init-db
python app.py
```

啟動後：

```text
http://127.0.0.1:8500
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:CARELOG_START_SCHEDULER="0"
flask --app app init-db
$env:CARELOG_START_SCHEDULER="1"
python app.py
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

停止與啟動：

```bash
docker compose stop
docker compose start
```

更新程式：

```bash
git pull --ff-only
docker compose up -d --build
```

## 5. Waitress＋systemd

建立專用帳號並安裝：

```bash
sudo useradd --system --home /opt/carelog --shell /usr/sbin/nologin carelog
sudo mkdir -p /opt/carelog /var/lib/carelog
sudo chown -R carelog:carelog /opt/carelog /var/lib/carelog
```

以 `carelog` 使用者建立虛擬環境、安裝套件與初始化資料庫。接著建立 `/etc/systemd/system/carelog.service`：

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

1. **Tailscale／WireGuard**：只有家庭成員裝置能連線，設定相對簡單。
2. **反向代理＋HTTPS**：Nginx、Caddy 或 NAS 內建反向代理將 HTTPS 轉送到 `127.0.0.1:8500`。

不要直接把 Flask 開發伺服器或未加密的 Waitress 埠暴露到 Internet。

## 7. Gmail 與排程

排程器必須只啟動一次。正式服務設 `CARELOG_START_SCHEDULER=1`；執行資料庫初始化、測試或其他一次性 CLI 指令時設為 `0`。

Gmail 請使用 Google 應用程式密碼。寄信失敗時先檢查：

- SMTP 帳號與應用程式密碼；
- 收件人格式；
- 主機能否連線到 Gmail SMTP；
- 容器或主機時區；
- 應用程式日誌。

## 8. 備份與還原

### 備份

先暫停服務，再複製整個資料目錄：

```bash
docker compose stop
cp -a data "data-backup-$(date +%Y%m%d-%H%M%S)"
docker compose start
```

或 systemd：

```bash
sudo systemctl stop carelog
sudo cp -a /var/lib/carelog "/var/backups/carelog-$(date +%Y%m%d-%H%M%S)"
sudo systemctl start carelog
```

### 還原

1. 停止 CareLog。
2. 將備份的 `carelog.db` 與 `uploads/` 放回相同資料目錄。
3. 確認檔案擁有者與權限。
4. 啟動服務並逐頁檢查。

備份若從未演練還原，只能算「充滿希望的複製品」，不能算可靠備份。

## 9. 從 1.0 升級至 1.1

1. 完整備份資料庫與照片。
2. 停止舊服務。
3. 更新程式與 Python 套件。
4. 執行：

```bash
CARELOG_START_SCHEDULER=0 flask --app app init-db
```

5. 啟動新服務。
6. 驗證：
   - 管理者可查看使用者刪除按鈕；
   - 管理者進入填報頁後仍可返回後台；
   - 照顧者可開啟儀表板；
   - 五種語言可切換；
   - 新增長輩生日預設為 1940-01-01；
   - 報表出現平均、最低、最高及次數。

本次資料模型未要求刪除既有照顧紀錄。刪除登入帳號時，系統保留歷史紀錄並清除其建立者關聯。

## 10. 故障檢查

```bash
python -m compileall -q .
python scripts/check_translations.py
python scripts/static_check.py
pytest
```

Docker：

```bash
docker compose ps
docker compose logs --tail=200 carelog
docker compose exec carelog flask --app app routes
```
