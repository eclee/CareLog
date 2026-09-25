# CareLog 1.4.0 系統架構

1.4.0 新增 `user_elder_access`、`login_attempts`、`med_plan_versions`，並由 `services/analytics.py` 統一液體攝取統計。舊資料庫須依 [UPGRADE_1_4.md](UPGRADE_1_4.md) 明確升級；下文保留既有模組的背景架構。

## 系統邊界

```text
照顧者手機 ─┐
家屬瀏覽器 ─┼─> Flask / Jinja / JSON API ─> SQLAlchemy ─> SQLite
管理者瀏覽器 ┘             │                    │
                            ├─> Media service ──> uploads/
                            ├─> Abnormal engine ─> abnormal_events
                            ├─> Report service ─> HTML / PDF
                            ├─> Mail service ────> Gmail SMTP
                            └─> APScheduler ─────> 報表、提醒、飲水結算
```

CareLog 採 server-rendered Jinja 頁面；儀表板透過 `/family/data` 取得 JSON，再由 Chart.js 繪圖。系統目前定位為單一家庭或小型照顧環境，尚未包含多租戶隔離。

## Application factory

`app.create_app()` 負責：

1. 載入環境設定；
2. 初始化 SQLAlchemy；
3. 檢查資料庫結構；對未升級的既有資料庫拒絕一般啟動，須在備份後明確執行 `upgrade-db`；
4. 註冊五個 Blueprint；
5. 注入使用者、語言、翻譯函式與待處理異常數量；
6. 視設定啟動單一排程器。

正式部署使用：

```bash
waitress-serve --call app:create_app
```

專案不在模組匯入時建立全域 app，因此不會因 Waitress 的 `--call` 再建立第二個排程器。

## Blueprint

| Blueprint | URL 前綴 | 職責 |
|---|---|---|
| `auth` | `/` | 登入、登出、語言切換 |
| `front` | `/care` | 照顧填報與前台照片上傳 |
| `family` | `/family` | 儀表板 JSON、趨勢頁及簡化照片頁 |
| `admin` | `/admin` | 長輩、用藥、使用者、參數、通知、稽核、照片、異常 |
| `media` | `/media` | 以圖片 ID 驗證權限後傳送原圖或縮圖 |

## 權限

- `admin`：所有後台、填報、儀表板、照片與異常事件處理。
- `worker`：填報、儀表板與照片。
- `family`：儀表板與照片。

`login_required(*roles)` 先確認 session 使用者仍存在、啟用且未被刪除，再核對角色。非管理者僅可查看 `UserElderAccess` 中授權的啟用長輩；一般頁面、儀表板 JSON、填報與媒體下載都會檢查此授權。升級時為既有帳號建立對既有長輩的授權，新長輩則由管理者明確指派。

## 長駐導覽列

`templates/_main_nav.html` 同時被 `base.html` 與 `base_front.html` 引用。管理者可在後台、儀表板、填報、照片及異常事件間切換；待確認／追蹤中的異常數量會顯示在導覽列。

## 核心資料模型

| 模型 | 主要內容 |
|---|---|
| `User` | 帳號、角色、密碼與 PIN 雜湊、語言、啟用及刪除時間；舊 `pin` 欄升級後清空 |
| `UserElderAccess` | 使用者對長輩的明確授權 |
| `LoginAttempt` | 以雜湊鍵保存的登入失敗次數與時間 |
| `Elder` | 姓名、生日、性別、血型、身高、聯絡、病史、過敏、就醫與緊急聯絡資料 |
| `ElderSetting` | 每位長輩的版本化 JSON 參數，目前保存健康數據填報預設值 |
| `MedPlan` | 長輩、藥名、時段、餐前／飯後、劑量 |
| `MedPlanVersion` | 用藥計畫快照及生效時間；舊計畫從升級日起建立首版 |
| `MedSubmission` | 一次用藥表單送出的群組，連結多筆用藥與共同照片 |
| `MealRecord` | 日期、時段、進食量、營養品、建立者 |
| `MedRecord` | 日期、用藥計畫、已給／未給、原因、填報群組 |
| `VitalRecord` | 體重、血壓、脈搏、血氧、時間、建立者 |
| `WaterRecord` | 日期、時間、喝水量、建立者 |
| `BowelRecord` | 日期、時間、Bristol 類型、建立者 |
| `Photo` | 用途、來源、長輩、日期、結構化路徑、縮圖、雜湊與上傳者 |
| `AbnormalEvent` | 異常類型、值、門檻快照、嚴重度、狀態、來源與處理紀錄 |
| `AuditLog` | 操作者快照、動作、類型、長輩、詳細內容與 JSON 中繼資料 |
| `Setting` | JSON 系統設定 |
| `SentLog` | 排程寄送去重複鍵 |

## 參數設定

`Setting.key = care_parameters` 保存版本化 JSON。`get_care_parameters()` 會把既有設定與 `DEFAULT_CARE_PARAMETERS` 深度合併，因此新增參數不會使舊資料庫缺少欄位。

目前參數包括：

- 喝水快捷值及單次上下限；
- 新增長輩的預設生日與喝水目標；
- 儀表板預設期間；
- 照顧填報與藥物參考圖片數量；
- 生命徵象、用藥、進食、排便與飲水不足規則。

安全密鑰、資料庫位置、上傳目錄、CSRF 與排程器開關仍由環境或部署設定管理，不提供網頁修改。

`Setting.key = reminders` 另保存未填報提醒總開關、四個時段的個別開關及截止時間。排程器先檢查總開關，再逐一略過未啟用的時段。舊設定缺少個別開關時以 `True` 深度合併，維持既有行為。

`ElderSetting.key = care_parameters` 保存個別長輩參數。目前 `vital_defaults` 包含體重、收縮壓、舒張壓、脈搏與血氧；空值代表前台不預先帶入。這些數值不參與異常規則，也不取代實際量測。

## 帳號管理語意

1. 只有使用者名稱為 `admin` 的內建系統帳號禁止刪除、停用、改名或變更角色；
2. 後續新增的管理者可由另一位管理者刪除，但目前登入中的帳號不能刪除自己；
3. 照顧者與家屬可在兩種角色間切換，切換時必須具備相應登入憑證；
4. 每個啟用帳號都必須具備 PIN 與密碼；照顧者以 PIN 登入，家屬與管理者以帳號／密碼登入。只有內建 `admin` 的角色固定，其他帳號可在三種角色間切換；
5. 可刪除帳號均採邏輯刪除：
   - 停用帳號並記錄 `deleted_at`；
   - 清除密碼雜湊或 PIN，阻止再次登入；
   - 從一般使用者管理清單隱藏；
   - 保留 `User` 資料列、照顧紀錄的 `created_by` 與歷史操作身分；
   - 新增帳號刪除稽核事件。

這是邏輯刪除，而不是物理刪除，目的是保全照顧事實與稽核可追溯性。

## 媒體架構

### 用途

`Photo.kind` 區分：

- `care_evidence`：餐飲、用藥、生命徵象及排便填報照片；
- `med_reference`：用藥計畫的藥物辨識圖片；
- `abnormal_followup`：異常事件的後續處理照片。

### 檔案結構

```text
uploads/elders/elder-000001/
├── care-records/2026/08/22/meal/record-000123/
├── care-records/2026/08/22/medication/submission-000045/
├── medication-plans/plan-000012/reference/
└── abnormal-events/event-000010/followup/
```

資料庫保存 POSIX 相對路徑，不保存姓名、病名或藥名於檔名。`services/media.py` 負責：

- 解碼與實際格式驗證；
- EXIF 方向校正；
- JPEG 正規化、縮放與縮圖；
- 雜湊、尺寸、檔案大小及 MIME 中繼資料；
- 部分失敗清理；
- 來源紀錄刪除時的媒體軟刪除；
- 舊版照片搬移。

瀏覽器只取得 `/media/photos/<id>` 或縮圖 URL。路由先查詢資料庫、確認登入與長輩狀態，再傳送檔案，並設定私有、不可快取的回應標頭。

## 異常事件流程

```text
保存照顧紀錄
→ 保存照片
→ 執行異常規則
→ 建立或更新 AbnormalEvent
→ 關聯來源照片
→ 提交資料庫
→ 嘗試寄送通知
→ 記錄通知結果
```

異常事件與寄信分離，因此 SMTP 未設定或寄送失敗不會遺失事件。每筆事件保存判定時的門檻快照，日後修改參數不會改寫既有事件的判定依據。

狀態包括：

- `pending`：待確認；
- `tracking`：追蹤中；
- `resolved`：已解除；
- `dismissed`：排除。

生命徵象一個量測可產生多筆指標事件；這些事件可以共同連結同一組圖片，不複製實體檔案。

## 操作紀錄與查詢

`AuditLog` 同時保存 `user_id` 與操作當時的帳號、姓名、角色快照。即使帳號日後停用、刪除或改名，歷史紀錄仍可理解。

查詢使用共用的 `services/query_filters.py`：

- 單一日期；
- 日期期間；
- 分頁筆數；
- 排序；
- 保留翻頁時的查詢參數。

照片庫及異常事件頁沿用相同日期與分頁規則。

## 統計定義

### 健康數據

每一項分別計算平均、最低、最高、發生時間與有效量測次數，空值不參與計算。

### 喝水

同日多筆白開水及營養品攝取量分開加總、分色顯示，合計作為液體總量。「有紀錄日平均／最低／最高」只採計有明確液體量的日期；另提供「全期間日均」，以期間總量除以完整天數。沒有填營養品容量時列為未知量，避免把它當作確定 0 ml。

### 用藥

儀表板分別列出已填報項目的給藥率，以及已知計畫期間的應服藥履行率。後者依 `MedPlanVersion` 快照計算應服藥次數，將「已給」、「未給」與「未填報」分開。升級前沒有保存計畫歷史，因此舊計畫只能從升級日開始成為已知分母。

## 資料庫升級與健檢

`services/schema.py` 提供明確執行、可重複執行的 SQLite 相容性升級；詳見 [1.4.0 升級指引](UPGRADE_1_4.md)：

- 新安裝以 SQLAlchemy metadata 建表；
- 1.1.x 既有表以 `ALTER TABLE ADD COLUMN` 補充欄位；
- 建立新資料表及索引；
- 回填舊照片的日期與上傳者；
- 回填仍可識別的操作人員快照；
- 補上長輩醫療基本資料欄位與 `elder_settings`；
- 雜湊並清除舊 PIN，回填既有使用者與長輩的授權，以及既有用藥計畫的升級日起始快照；
- 以 `schema_health()`／`check-db` 驗證必要資料表與欄位。

請求期間若 SQLite 回報缺少資料表或欄位，應用程式會回傳可操作的 503 診斷頁。舊照片日期完全缺漏時使用 `Photo.display_date` 安全回退，不讓照片檢索因空值發生 500。

這不是 Alembic 的完整版本歷史。若未來出現複雜欄位重命名、資料拆表或多資料庫支援，應導入正式 migration 工具。

## 已知擴充方向

- 多家庭／多機構租戶隔離；
- 多因素驗證及更完整的權限分層；
- 正式 Alembic migration；
- 本機化 Bootstrap、Chart.js 與字型資源；
- 資料保存期限、匯出、刪除及同意管理；
- 升級前用藥歷史的外部匯入與稽核；
- 異常通知重試、簡訊或即時通訊管道。
