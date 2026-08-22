# CareLog 居家照顧填報與管理平台

[English](README.en.md)

CareLog 是以 Python Flask 開發的單一家庭或小型居家照顧協作平台。照顧者可用手機填報餐飲、用藥、健康數據、喝水與排便；家屬及照顧者可查看趨勢儀表板；管理者則負責長輩、用藥計畫、帳號、參數、通知、照片、異常事件與報表。

> CareLog 是照顧溝通工具，不是醫療器材、診斷系統、用藥指示或緊急通報服務。正式使用前請閱讀 [DISCLAIMER.md](DISCLAIMER.md) 與 [SECURITY.md](SECURITY.md)。

## 1.2.0 主要功能

### 彈性參數

- 後台「參數設定」可調整三個喝水快捷值、單次喝水上下限、新增長輩的預設生日與喝水目標、儀表板預設期間及圖片數量上限。
- 異常規則可設定生命徵象門檻、未給藥、異常排便、未進食、少量進食及每日飲水不足。
- 預設值只套用於後續操作，不會回溯覆寫既有長輩資料。

### 用藥圖片

- 管理者可在建立或編輯用藥計畫時直接拍照或上傳藥錠、藥袋、藥盒及劑量示意圖。
- 每項用藥可保留多張參考圖並指定主圖。
- 照顧者填報用藥時會同時看到藥名、劑量及藥物參考圖片。
- 藥物圖片只協助辨識，正式給藥仍應依醫囑、藥袋與文字用量確認。

### 結構化照片庫

新上傳照片會依用途分層保存，例如：

```text
uploads/
└── elders/
    └── elder-000001/
        ├── care-records/2026/08/22/vital/record-000123/
        ├── care-records/2026/08/22/medication/submission-000045/
        ├── medication-plans/plan-000012/reference/
        └── abnormal-events/event-000010/followup/
```

系統會：

- 驗證並正規化圖片為 JPEG；
- 移除 EXIF 方向問題並產生縮圖；
- 保存檔案大小、尺寸、雜湊值、上傳者、紀錄日期及來源紀錄；
- 以圖片 ID 經權限檢查後傳送，不公開實體檔案路徑；
- 讓管理者依長輩、用途、紀錄類型、紀錄 ID、上傳者、日期及異常關聯篩選。

### 操作紀錄與異常事件

- 操作紀錄可依使用者、角色、動作、紀錄類型、長輩、關鍵字、特定日期或日期期間查詢並分頁。
- 帳號刪除採停用式刪除：移除登入憑證，但保留歷史身分、照顧紀錄與操作軌跡。
- 異常事件會永久保存，不會因 Email 寄送失敗而消失。
- 支援生命徵象超標、未給藥、異常排便、進食異常與選用的每日飲水不足。
- 管理者可將事件標示為「待確認、追蹤中、已解除、排除」，填寫處理說明並查看來源資料及圖片。

### 既有功能

- 五種照顧者介面語言：繁體中文、印尼語、越南語、Filipino、泰語。
- 自動載入 `locales/*.json`，便於增加其他語言。
- 管理者、家屬與照顧者依角色顯示長駐式上方導覽列。
- 照顧者可查看綜合儀表板與照片。
- 儀表板顯示平均、最低、最高及量測次數；HTML Email 與 PDF 報表另顯示最低／最高值的發生時間。
- 使用者管理頁採較緊湊的字體與版面，不影響照顧者端的大按鈕介面。

## 角色與權限

| 角色 | 登入方式 | 可使用功能 |
|---|---|---|
| 照顧者 `worker` | 選擇姓名＋PIN | 填報、趨勢儀表板、照片、語言切換 |
| 家屬 `family` | 帳號＋密碼 | 趨勢儀表板、照片、語言切換 |
| 管理者 `admin` | 帳號＋密碼 | 全部後台、填報、儀表板、照片與異常處理 |

CareLog 目前仍以單一家庭為設計前提；所有啟用中的使用者可依角色查看啟用中的長輩。多家庭／機構租戶隔離尚未實作。

## 快速開始：Python

需求：Python 3.10–3.13。

```bash
cd CareLog-1.2.0
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# macOS / Linux：建立隨機 session 金鑰
export CARELOG_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# 建立／升級資料表與預設管理者：admin / care1234
CARELOG_START_SCHEDULER=0 flask --app app init-db

# 選用：建立示範長輩、照顧者與家屬
CARELOG_START_SCHEDULER=0 flask --app app seed-demo

python app.py
```

瀏覽器開啟 `http://127.0.0.1:8500`。同一區域網路的手機可使用 `http://<主機IP>:8500`。

### 使用 uv

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
CARELOG_START_SCHEDULER=0 uv run flask --app app init-db
uv run python app.py
```

## 快速開始：Docker Compose

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# 將輸出的隨機值填入 .env 的 CARELOG_SECRET

docker compose up -d --build
```

開啟 `http://127.0.0.1:8501`。SQLite、照片及設定保存在 `data/`；重建容器不會刪除該目錄。

## 從 1.1.0 升級

先停止服務並備份資料庫與照片，再執行：

```bash
CARELOG_START_SCHEDULER=0 flask --app app upgrade-db
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --dry-run
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --apply
```

需要用目前規則重建舊資料的異常事件時，可選擇日期範圍：

```bash
CARELOG_START_SCHEDULER=0 flask --app app rebuild-abnormal-events \
  --from-date 2026-01-01 --to-date 2026-08-22
```

歷史異常重建使用「執行當下」的規則，不能還原當時尚未保存的門檻設定。完整步驟請見 [docs/UPGRADE.md](docs/UPGRADE.md)。Docker 啟動時會自動執行相容性升級，但仍應先做可還原的備份。

## 必做的首次設定

1. 以 `admin / care1234` 登入。
2. 立即在「使用者與角色管理」更換管理者密碼。
3. 新增實際長輩與照顧者，刪除或停用示範帳號。
4. 到「參數設定」確認喝水快捷值、預設生日、異常門檻及圖片限制。
5. 設定強度足夠且不重複的 PIN／密碼。
6. 正式環境設定隨機 `CARELOG_SECRET`。
7. 使用 HTTPS 反向代理或 Tailscale／WireGuard，不要直接將開發伺服器暴露於 Internet。

## Gmail、排程與 PDF

後台「通知設定」可填 Gmail 帳號、Google 應用程式密碼、收件人與報表排程。生命徵象異常會先保存為事件，再嘗試寄送通知；寄信失敗時仍可在後台查詢。

若要產生中文字型 PDF，將可合法使用的字型命名為：

```text
fonts/NotoSansTC-Regular.ttf
```

字型檔不包含在專案中，也不應任意重新散布。

## 新增語言

```bash
cp locales/zh.json locales/ja.json
# 修改 ja.json 的 _meta 與所有翻譯
python scripts/check_translations.py
```

詳見 [docs/LOCALIZATION.md](docs/LOCALIZATION.md)。

## 測試與品質檢查

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q .
python scripts/check_translations.py
python scripts/static_check.py
python -m pytest
```

或執行：

```bash
make check
```

GitHub Actions 會在 Python 3.10、3.12 與 3.13 執行相同檢查。

## 上傳到 GitHub

```bash
git init
git status --short
git add -- .dockerignore .env.example .gitattributes .github .gitignore \
  CHANGELOG.md CODE_OF_CONDUCT.md CONTRIBUTING.md DISCLAIMER.md Dockerfile LICENSE \
  Makefile README.md README.en.md SECURITY.md VERSION app.py config.py docker-compose.yml \
  docker-entrypoint.sh docs fonts locales models.py pyproject.toml requirements-dev.txt \
  requirements.txt routes scripts security.py services static templates tests \
  translations.py uploads utils.py
git commit -m "feat: release CareLog 1.2.0"
git branch -M main
git remote add origin git@github.com:<OWNER>/<REPOSITORY>.git
git push -u origin main
```

發布前請依 [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) 檢查，尤其不要提交 `.env`、資料庫、`data/`、照片、字型、備份或真實健康資料。

## 專案結構

```text
CareLog-1.2.0/
├── app.py                       # Flask application factory、CLI、排程
├── config.py                    # 環境與儲存設定
├── models.py                    # SQLAlchemy 資料模型與參數預設
├── routes/                      # auth、front、family、admin、media
├── services/                    # 媒體、異常、報表、郵件、排程、升級
├── templates/                   # Jinja 頁面與長駐主選單
├── locales/                     # 五種語言 JSON
├── tests/                       # 功能測試
├── scripts/                     # 翻譯與離線靜態檢查
├── docs/                        # 建置、架構、升級、在地化與發布文件
├── .github/                     # CI、Dependabot、Issue／PR 範本
├── Dockerfile
└── docker-compose.yml
```

## 開源與貢獻

- 授權：[MIT License](LICENSE)
- 貢獻：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全問題：[SECURITY.md](SECURITY.md)
- 版本變更：[CHANGELOG.md](CHANGELOG.md)
- 系統架構：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 建置部署：[docs/BUILD_AND_DEPLOY.md](docs/BUILD_AND_DEPLOY.md)
