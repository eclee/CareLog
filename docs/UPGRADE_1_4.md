# CareLog 1.4.0：資料庫升級與回復

適用來源：正式使用的 1.3.2 SQLite 資料庫。1.1／1.2 使用者請先依 [舊版升級指引](UPGRADE.md) 升至 1.3.2 並驗收，再依本文件升級。不要讓兩版程式同時寫入同一份資料庫。**資料庫升級與 PIN 明文清除後，不能用舊版程式繼續寫入；回復必須連同升級前資料庫及照片一併還原。**

## 升級改變了什麼

| 資料 | 升級動作 | 舊資料如何保留 |
|---|---|---|
| `users` | 新增 `pin_hash`；以 Werkzeug 雜湊既有 `pin`，再清空明文欄位 | 帳號、密碼雜湊、角色、操作紀錄及原 PIN 的登入能力保留；原始 PIN 無法從雜湊還原 |
| `user_elder_access` | 新增使用者與長輩授權表 | 升級當下，既有啟用帳號對既有啟用長輩全部回填授權，維持 1.3.2 可見範圍；新帳號及新長輩須由管理者選擇授權 |
| `med_plan_versions` | 對既有用藥計畫建立從**升級當天**生效的快照 | 舊 `med_plans` 及 `med_records` 不刪除；升級前的計畫異動歷史不可還原，不納入「應服藥計畫履行率」分母 |
| `med_records` | 新增可空的 `plan_version_id` | 舊用藥紀錄維持原關聯，新填報紀錄連結當時的計畫版本 |
| 體重、液體及排便 | 沿用既有資料表 | 舊體重不改寫；以原餐飲 `supplement_cc` 與喝水 `amount` 分項重算；沒有填 cc 的營養品量維持未知 |

目標資料庫結構版本是 **4**。`check-db` 檢查版本、必要資料表和欄位，也檢查是否殘留明文 PIN；它不能代替頁面及照片驗收。遷移可重複執行，但**仍須先備份**。新版偵測到舊版資料庫時不會在網站啟動期間偷偷修改它；會拒絕啟動並提示執行升級命令。

## 0. 找出真正的資料路徑

- Python 未設定 `CARELOG_DATA`：專案根目錄中的 `carelog.db` 與 `uploads/`。
- Python 已設定 `CARELOG_DATA`：`$CARELOG_DATA/carelog.db` 與 `$CARELOG_DATA/uploads/`。
- 預設 Docker Compose：宿主機 `./data/carelog.db` 與 `./data/uploads/`，容器內 `/data/`。

先確認實際路徑與備份磁碟空間，不要對另一個空白資料庫執行升級。照片與資料庫是一組資料，須一起備份及回復。

## 1. 停機、取回新版程式及備份

先停止所有寫入者、排程器與舊容器；Docker 使用 `docker compose down`。更新程式檔後、**尚未執行新版應用程式**時，用獨立備份腳本（不匯入 Flask，也不觸發遷移）建立備份：

```bash
# Python 預設資料路徑：在新版專案根目錄執行
python scripts/backup_data.py --data . --output ../carelog-backup-before-1.4

# 自訂 CARELOG_DATA：改用原本的正式資料目錄
python scripts/backup_data.py --data /實際資料目錄 --output /另一磁碟/carelog-backup-before-1.4

# Docker Compose：停機後在專案根目錄執行
python scripts/backup_data.py --data ./data --output ../carelog-backup-before-1.4
```

輸出目錄必須不存在。腳本透過 SQLite backup API 建立一致的 `carelog.db`、執行 `PRAGMA integrity_check`、複製 `uploads/`，並建立 `manifest.json`（資料庫 SHA-256 和照片檔數）。核對備份目錄含資料庫及應有照片；建議另存於與正式資料不同的磁碟。備份中含健康資料及登入資訊，應限制存取。

## 2. 先以備份副本試升級

```bash
cp -a ../carelog-backup-before-1.4 ../carelog-migration-trial
CARELOG_DATA="$(cd ../carelog-migration-trial && pwd)" \
CARELOG_ALLOW_UPGRADE=1 CARELOG_START_SCHEDULER=0 \
python -m flask --app app upgrade-db

CARELOG_DATA="$(cd ../carelog-migration-trial && pwd)" \
CARELOG_START_SCHEDULER=0 python -m flask --app app check-db
```

`CARELOG_ALLOW_UPGRADE=1` **只用於升級命令**；不要放入正式 `.env`。若只在 Docker 中安裝 Python 依賴，可先 `docker compose build`，再以單次容器掛載試驗目錄：

```bash
docker run --rm --env-file .env -e CARELOG_ALLOW_UPGRADE=1 \
  -e CARELOG_START_SCHEDULER=0 -e CARELOG_DATA=/trial \
  -v "$(cd ../carelog-migration-trial && pwd):/trial" \
  carelog:1.4.0 flask --app app upgrade-db
```

確認試升級後的長輩、使用者、五種填報紀錄與照片筆數相符；以測試帳號登入副本，查看儀表板、照片、報表及用藥計畫。舊照顧者 PIN 應仍可登入，資料庫 `users.pin` 應全為 `NULL`。不要把試驗副本拿來繼續正式填報。

## 3. 升級正式資料庫

保持服務停止，且已確認備份與試升級成功。Python 部署：

```bash
export CARELOG_DATA=/實際資料目錄   # 未使用此設定者省略此行
CARELOG_ALLOW_UPGRADE=1 CARELOG_START_SCHEDULER=0 \
  python -m flask --app app upgrade-db
CARELOG_START_SCHEDULER=0 python -m flask --app app check-db
```

Docker Compose 部署：

```bash
docker compose build
docker compose run --rm -e CARELOG_ALLOW_UPGRADE=1 \
  -e CARELOG_START_SCHEDULER=0 carelog flask --app app upgrade-db
docker compose run --rm -e CARELOG_START_SCHEDULER=0 \
  carelog flask --app app check-db
docker compose up -d
```

正常的 `check-db` 輸出應顯示**預期的資料庫路徑**、目標版本 **4** 和「資料庫結構檢查通過」。Docker entrypoint 會在 Waitress 啟動前再次執行 `check-db`；舊版或不完整結構不應帶病上線。升級失敗時不要反覆啟動網站：保留錯誤訊息，檢查備份，必要時依「回復」操作。

## 4. 頁面驗收

1. 舊管理者、家屬、照顧者登入，原本可看的長輩仍可見；新增帳號及新增長輩的授權由管理者指定，未授權的照片 ID／儀表板 API 不可讀。
2. 填報 `55.27 kg`，核對當日列表、圖表提示、摘要平均／最小／最大與 HTML／PDF 報表均顯示兩位小數。
3. 同一天填白開水及有 cc 的營養品，檢查分色堆疊圖、合計及報表；僅勾營養品但未填 cc 應顯示量未知，不應當作已知 0 ml。
4. 使用跨月份的自訂起訖日期，確認首日與末日均納入；排便七型圖表的總和等於期間紀錄次數。
5. 編輯或停用用藥計畫後確認新增版本；「已填報項目給藥率」與「應服藥計畫履行率」分列，後者不回推至升級前日期。
6. 確認相片原圖與縮圖可讀、異常事件可查、通知排程沒有重複啟動。

## 5. 回復（不可直接把新版資料庫交給舊程式）

停止新版服務。將目前資料目錄移到隔離位置以免覆蓋，從 `carelog-backup-before-1.4` 還原 `carelog.db` 和整個 `uploads/`，確認照片數量及資料庫完整性；再切回 **1.3.2 程式碼／映像檔**啟動，抽查登入與照顧紀錄。若新版本已接受正式填報，回復至升級前備份會失去這段期間新寫入的資料；須先匯出或人工處理這些變更，不能兩版同時寫同一資料庫。

Docker 宿主機回復範例（在 `docker compose down` 後）：

```bash
mv data "data-failed-1.4"
mkdir data
cp ../carelog-backup-before-1.4/carelog.db data/
cp -a ../carelog-backup-before-1.4/uploads data/
# 切回 1.3.2 的程式碼／映像檔後再啟動
```

## 注意事項

- 用藥計畫在升級前沒有版本歷史，不能以今天看到的啟用狀態推算過去每一天應服的藥。
- 登入限流以 `request.remote_addr` 辨識來源；若所有用戶都經同一反向代理，須先正確設定**可信代理**的來源 IP 傳遞，否則共同 IP 可能一起達到限流門檻。不能直接信任用戶送來的 `X-Forwarded-For`。
- 若舊資料庫有缺表／缺欄、硬碟空間不足或特殊客製欄位，先在副本驗證；SQLite DDL 不保證整個複雜遷移可由單一交易全數回滾，所以正式回復依賴升級前完整備份。
- 首次啟動預設管理帳號仍可能是 `admin / care1234`、PIN `1234`；立即更換，設定隨機 `CARELOG_SECRET`，並透過 HTTPS 或私人網路使用。
