# CareLog 系統架構

## 系統邊界

```text
照顧者手機 ─┐
家屬瀏覽器 ─┼─> Flask / Jinja / JSON API ─> SQLAlchemy ─> SQLite
管理者瀏覽器 ┘             │                    │
                            ├─> Pillow ─────────> uploads/
                            ├─> Report service ─> HTML / PDF
                            ├─> Alert service ──> Gmail SMTP
                            └─> APScheduler ────> 定期報表與提醒
```

CareLog 採 server-rendered Jinja 頁面；儀表板透過 `/family/data` 取得 JSON，再由 Chart.js 繪圖。

## Application factory

`app.create_app()` 負責：

1. 載入設定；
2. 初始化 SQLAlchemy；
3. 執行輕量相容性處理；
4. 註冊四個 Blueprint；
5. 注入使用者、語言與翻譯函式；
6. 視設定啟動單一排程器。

正式部署使用：

```bash
waitress-serve --call app:create_app
```

專案不在模組匯入時預先建立另一個 app，因此不會因 `--call` 重複啟動排程器。

## Blueprint

| Blueprint | URL 前綴 | 職責 |
|---|---|---|
| `auth` | `/` | 登入、登出、語言切換 |
| `front` | `/care` | 照顧填報、照片傳送 |
| `family` | `/family` | 儀表板 JSON、趨勢頁、照片頁 |
| `admin` | `/admin` | 長輩、用藥、使用者、通知、稽核 |

## 權限

- `admin`：所有後台、填報、儀表板與照片。
- `worker`：填報、儀表板與照片。
- `family`：儀表板與照片。

`login_required(*roles)` 先確認 session 中的使用者仍存在且啟用，再核對角色。

## 長駐導覽列

`templates/_main_nav.html` 同時被 `base.html` 與 `base_front.html` 引用。導覽項目由角色決定，並以 sticky CSS 固定於頁面頂端。新增主要功能時，只需在這個 partial 增加角色條件與連結。

## 資料模型

| 模型 | 主要內容 |
|---|---|
| `User` | 帳號、角色、密碼雜湊／PIN、語言、啟用狀態 |
| `Elder` | 姓名、生日、備註、喝水目標、啟用狀態 |
| `MedPlan` | 長輩、藥名、時段、餐前／飯後、劑量 |
| `MealRecord` | 日期、時段、進食量、營養品、建立者 |
| `MedRecord` | 日期、用藥計畫、已給／未給、原因、建立者 |
| `VitalRecord` | 體重、血壓、脈搏、血氧、時間、建立者 |
| `WaterRecord` | 日期、時間、喝水量、建立者 |
| `BowelRecord` | 日期、時間、Bristol 類型、建立者 |
| `Photo` | 紀錄類型、紀錄 ID、長輩、檔案路徑 |
| `Setting` | JSON 系統設定 |
| `AuditLog` | 建立、修改、刪除操作 |
| `SentLog` | 排程寄送去重複鍵 |

## 帳號刪除語意

帳號刪除是「刪除登入身分、保留照顧事實」：

1. 禁止刪除目前登入者；
2. 禁止刪除最後一位啟用中的管理者；
3. 將該帳號建立的照顧紀錄 `created_by` 改成 `NULL`；
4. 將該帳號過去操作紀錄的 `user_id` 改成 `NULL`；
5. 以目前管理者身分建立帳號刪除稽核事件；
6. 刪除 `User` 資料列。

這樣可避免歷史報表被連帶刪除，也避免資料庫外鍵懸空。需要完整保留操作者歷史身分的機構型部署，應改採停用或匿名化帳號，而不是硬刪除。

## 統計定義

### 健康數據

每一項數值分別計算：

- 平均；
- 最低值與發生時間；
- 最高值與發生時間；
- 有效量測次數。

空值不參與該項計算。

### 喝水

系統先將同一天的多筆喝水紀錄加總。摘要中的「平均、最低、最高」只採計有紀錄的日期，避免把資料缺漏直接宣告為喝水 0 ml；另提供「全期間日均」，以期間總量除以完整天數，並顯示「有紀錄天數／期間天數」。儀表板趨勢圖對未填日期保留空值，使「未填」與「確定為 0」不被混為一談。

### 用藥

目前完成率仍以「已填報的用藥項目」為分母。若要計算真正的應服藥遵從率，後續版本應為 `MedPlan` 增加生效日、停用日與版本歷史，再依每日應服計畫建立分母。

## 多語架構

`translations.py` 掃描 `locales/*.json`，由 `_meta.order` 排序，並檢查所有語言的翻譯鍵與繁中一致。Jinja 使用 `t()` 與 `tf()`；路由使用 `tr()` 與 `tr_format()`。

## 已知擴充方向

- 多家庭／多機構租戶隔離；
- 使用者－長輩細緻授權；
- 登入限流、PIN 雜湊與多因素驗證；
- 正式 schema migration；
- 本機化 Bootstrap、Chart.js 與字型資源；
- 醫療／照顧資料保存期限、匯出與刪除流程；
- 用藥計畫版本化與真正的應服藥遵從率。
