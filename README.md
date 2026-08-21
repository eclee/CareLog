# CareLog 居家照顧填報與管理平台

[English](README.en.md)

CareLog 是以 Python Flask 開發的單一家庭居家照顧協作平台。照顧者可用手機填報餐飲、用藥、健康數據、喝水與排便；家屬與照顧者可查看趨勢儀表板；管理者則負責長輩、用藥計畫、帳號、通知及報表設定。

> CareLog 是照顧溝通工具，不是醫療器材、診斷系統、用藥指示或緊急通報服務。正式使用前請閱讀 [DISCLAIMER.md](DISCLAIMER.md) 與 [SECURITY.md](SECURITY.md)。

## 1.1.0 主要功能

- **帳號刪除**：管理者可刪除帳號；不能刪除自己，也不能刪除最後一位啟用中的管理者。歷史照顧紀錄保留，建立者欄位改為未指定。
- **長駐主選單**：登入後，依角色在所有主要頁面固定顯示「後台、儀表板、填報、照片、語言與登出」。
- **完整數值摘要**：儀表板、HTML Email 與 PDF 報表提供平均、最低、最高、發生時間及量測次數；喝水量亦呈現期間最低與最高日。
- **五種介面語言**：繁體中文、印尼語、越南語、Filipino、泰語。
- **多語異常提示**：健康數據超過警戒值時，照顧者畫面會使用目前選定的語言顯示警示。
- **可擴充語言架構**：系統自動載入 `locales/*.json`；新增語言不需修改 Python、路由或模板。
- **照顧者儀表板**：`worker` 除了填報，也能查看被照顧長輩的綜合趨勢與照片。
- **生日預設值**：新增長輩時預設為 `1940-01-01`，仍可直接改成實際日期。

## 角色與權限

| 角色 | 登入方式 | 可使用功能 |
|---|---|---|
| 照顧者 `worker` | 選擇姓名＋PIN | 填報、趨勢儀表板、照片、語言切換 |
| 家屬 `family` | 帳號＋密碼 | 趨勢儀表板、照片、語言切換 |
| 管理者 `admin` | 帳號＋密碼 | 後台全部功能、填報、儀表板、照片 |

## 填報與報表

- 餐飲：早上、中午、晚上、睡前；包含進食量、營養品與照片。
- 用藥：依時段、餐前／飯後及用藥計畫逐項填報。
- 健康數據：體重、收縮壓、舒張壓、脈搏、血氧與照片。
- 喝水：可多次新增，統計每日總量。
- 排便：Bristol 1–7 型、備註與照片。
- 通知：Gmail SMTP、異常數值警示、未填提醒、每日／每週／最近 30 日報表。
- 報表：HTML Email；放入中文字型後可附 PDF。

## 快速開始：Python

需求：Python 3.10–3.13。

```bash
cd carelog
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# macOS / Linux：建立隨機 session 金鑰
export CARELOG_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# 建立資料表與預設管理者：admin / care1234
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

開啟 `http://127.0.0.1:8501`。SQLite、照片及設定保存在 `data/`；升級或重建容器不會刪除該目錄。

更完整的本機、NAS、systemd、反向代理、備份與升級步驟，請參閱 [docs/BUILD_AND_DEPLOY.md](docs/BUILD_AND_DEPLOY.md)。

## 必做的首次設定

1. 以 `admin / care1234` 登入。
2. 立即在「使用者管理」更換管理者密碼。
3. 新增實際長輩與照顧者，刪除或停用示範帳號。
4. 設定強度足夠且不重複的 PIN／密碼。
5. 正式環境設定隨機 `CARELOG_SECRET`。
6. 使用 HTTPS 反向代理或 Tailscale／WireGuard，不要直接將開發伺服器暴露於 Internet。

## Gmail 與 PDF

### Gmail

後台「通知設定」可填 Gmail 帳號、Google 應用程式密碼與收件人。請勿使用一般 Google 密碼。

### PDF 字型

將可合法使用的繁中文字型命名為：

```text
fonts/NotoSansTC-Regular.ttf
```

系統可將變數字型轉成靜態字型；若字型不存在或 PDF 產生失敗，Email 仍會以 HTML 內文寄送。字型檔不包含在專案中，也不應任意重新散布。

## 新增語言

每個語言只有一個 JSON 檔，內容包含 `_meta` 與全部翻譯鍵：

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
pytest
```

或執行：

```bash
make check
```

GitHub Actions 會在 Python 3.10、3.12 與 3.13 重跑上述檢查。

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
git commit -m "feat: publish CareLog 1.1.0"
git branch -M main
git remote add origin git@github.com:<OWNER>/<REPOSITORY>.git
git push -u origin main
```

發布前請依 [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) 檢查，尤其不要提交 `.env`、`carelog.db`、`data/`、照片、字型或真實健康資料。

## 專案結構

```text
carelog/
├── app.py                       # Flask application factory、CLI、排程
├── config.py                    # 環境與儲存設定
├── models.py                    # SQLAlchemy 資料模型
├── translations.py             # 自動載入 locales/*.json
├── routes/                      # auth、front、family、admin
├── services/                    # mailer、alerts、reports、scheduler
├── templates/                   # Jinja 頁面與長駐主選單
├── locales/                     # 五種語言 JSON
├── tests/                       # 功能測試
├── scripts/                     # 翻譯與離線靜態檢查
├── docs/                        # 建置、架構、在地化、發布文件
├── .github/                     # CI、Dependabot、Issue／PR 範本
├── Dockerfile
└── docker-compose.yml
```

## 開源與貢獻

- 授權：[MIT License](LICENSE)
- 貢獻：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全問題：[SECURITY.md](SECURITY.md)
- 版本變更：[CHANGELOG.md](CHANGELOG.md)
- 架構：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
