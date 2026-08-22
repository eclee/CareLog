# 升級至 CareLog 1.3.2

本版支援由 CareLog 1.1.x、1.2.x、1.3.0 或 1.3.1 的 SQLite 資料庫接續使用。由 1.3.0／1.3.1 升級至 1.3.2 **沒有新增資料表或欄位**，可直接沿用既有資料庫與 `uploads/`；較舊版本仍會由既有相容程序就地補齊結構。1.3.2 主要修正 Gmail 應用程式密碼的隱藏空白編碼錯誤、雙憑證必填與角色調整規則。

> 由 1.1／1.2 升級仍屬單向流程；由 1.3.0／1.3.1 升級至 1.3.2 沒有結構變更，但仍不要讓不同版本同時寫入同一份 SQLite 資料庫。

## 一、先確認真正的資料目錄

Python 預設資料位置是專案目錄；若設定 `CARELOG_DATA`，則使用：

```text
$CARELOG_DATA/carelog.db
$CARELOG_DATA/uploads/
```

Docker 預設掛載：

```text
./data/carelog.db
./data/uploads/
```

新版解壓到另一個目錄後，最常見的錯誤不是資料消失，而是新版連到新的空白 `data/`。先記錄舊系統實際的資料路徑。

## 二、停止服務並完整備份

至少備份資料庫與照片：

```text
carelog.db
uploads/
```

Docker：

```bash
docker compose down
cp -a data "data-backup-$(date +%Y%m%d-%H%M%S)"
```

直接執行 Python／systemd 時，停止服務後複製整個 `CARELOG_DATA`。確認備份中確實存在資料庫及照片，並保留舊版程式碼或 release ZIP。

## 三、更新程式與依賴

```bash
git pull --ff-only
python -m pip install --upgrade -r requirements.txt
```

ZIP 使用者請把 1.3.2 放在新目錄，保留舊 `.env` 與資料目錄，並讓 `CARELOG_DATA` 指向原資料。不要把 `.git`、資料庫及照片當成新版程式檔覆蓋掉。

## 四、升級並健檢資料庫

```bash
CARELOG_START_SCHEDULER=0 flask --app app upgrade-db
CARELOG_START_SCHEDULER=0 flask --app app check-db
```

`upgrade-db` 可重複執行。它會補上或建立：

- 長輩性別、ABO／Rh 血型、身高、聯絡、過敏、病史、就醫及緊急聯絡欄位；
- `elder_settings` 個別長輩參數表；
- 使用者邏輯刪除欄位；
- 用藥填報群組；
- 結構化照片中繼資料；
- 操作者快照；
- 異常事件與圖片關聯；
- 查詢索引及結構版本。

正常的 `check-db` 會顯示實際 SQLite 路徑、目標版本 `3` 與「資料庫結構檢查通過」。若顯示的路徑不是預期資料，先修正 `CARELOG_DATA` 或 Docker volume，再做任何寫入。

Docker 亦可明確執行：

```bash
docker compose run --rm -e CARELOG_START_SCHEDULER=0 \
  carelog flask --app app upgrade-db

docker compose run --rm -e CARELOG_START_SCHEDULER=0 \
  carelog flask --app app check-db
```

Docker entrypoint 每次啟動都會執行 `init-db` 與 `check-db`；健檢失敗時不會啟動 Waitress。

## 五、舊照片搬移

資料庫升級後，舊路徑照片仍可讀；結構化搬移可另行進行。

先預覽：

```bash
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --dry-run
```

確認統計後套用：

```bash
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --apply
```

搬移會解碼原圖、正規化為 JPEG、產生縮圖、更新路徑與中繼資料，並在資料庫成功提交後才移除舊檔。找不到來源檔會列為 `missing`，不會假裝成功。

舊資料若同時缺少照片紀錄日期與上傳時間，1.3.2 會顯示「日期未記錄」，不再因 `NULL.date()` 造成 500。

## 六、照片管理或異常狀態出現 Internal Server Error

1.3.0 有一個與資料庫無關的模板錯誤：照片管理、異常狀態、操作紀錄、長輩資料與個別參數頁，會在送出 `elder`、`user`、`uploader`、`creator` 或 `per_page` 等數字型篩選值時，嘗試在 Jinja 中使用不存在的 Python `int` 全域名稱。頁面初次開啟可能正常，送出篩選才會發生 `UndefinedError: 'int' is undefined` 並回傳 500。即使使用全新資料庫也會發生。

1.3.2 已改用安全的字串比對並加入回歸測試。升級程式碼後，這類篩選錯誤不需要重建資料庫。仍建議依序檢查：

1. 更新至 1.3.2 並重新建置／重新啟動服務；
2. 執行 `check-db`，確認沒有真正缺少欄位或資料表；
3. 核對輸出的資料庫路徑是否為正式資料庫；
4. 查看應用程式或 Docker 日誌的原始例外；
5. 確認 `uploads/` 與資料庫位於同一資料目錄。

若 `check-db` 顯示缺少 `photos.kind`、`photos.record_date`、`abnormal_events` 或 `abnormal_event_photos`，才代表同一份資料庫尚未完成 1.2+ 結構升級，請執行 `upgrade-db`。

## 七、帳號管理差異

- 只有系統內建且使用者名稱為 `admin` 的帳號不可刪除；這項限制同時存在於畫面與伺服器端。
- 後續新增的管理者可由另一位管理者刪除，但目前登入中的帳號不可刪除自己。
- 新增任何角色時，PIN 與密碼都必填；PIN 限 4–16 位數字。
- 編輯既有帳號時，PIN／密碼留空代表保留原值；舊帳號缺少其中一項時，畫面與後端會要求補齊。
- 只有內建 `admin` 的角色不可修改；其他帳號可在管理者、家屬與照顧者之間切換。
- 家屬與管理者仍以帳號／密碼登入，照顧者仍以 PIN 登入。
- 帳號刪除仍採邏輯刪除，保留歷史照顧紀錄與稽核身分。
- 1.1 已物理刪除且清空 `user_id` 的歷史紀錄，若無其他線索，無法還原原操作者。

## 八、Gmail 測試郵件的 ASCII 編碼錯誤

若舊版曾出現：

```text
'ascii' codec can't encode character '\xa0'
```

通常是 Google 應用程式密碼的分組空白被複製成 `U+00A0` 或 `U+202F`，也可能混入零寬字元。1.3.2 會在通知設定儲存時及每次寄送前雙重正規化，因此既有已儲存設定通常不必重輸。若仍無法登入 Gmail，請重新產生應用程式密碼，並確認使用的是應用程式密碼而非一般帳號密碼。

## 九、個別長輩參數

升級後，每位長輩可在「後台 → 參數設定」擁有不同的體重、收縮壓、舒張壓、脈搏及血氧填報預設值。既有長輩預設為空，不會擅自帶入假造量測值。

## 十、選用：重建歷史異常事件

1.1.0 沒有永久異常事件表。需要時可使用目前規則回填：

```bash
CARELOG_START_SCHEDULER=0 flask --app app rebuild-abnormal-events \
  --from-date 2026-01-01 --to-date 2026-08-22
```

回填使用執行當下的規則，不能代表事件發生當時尚未保存的門檻；重建生命徵象不寄送 Email，相同來源與指標會用事件鍵去重複。

## 十一、啟動與驗收

```bash
CARELOG_START_SCHEDULER=0 flask --app app check-db
python app.py
```

至少驗證：

- 長輩基本資料可新增及編輯全部醫療欄位；
- 內建 `admin` 沒有刪除按鈕；後續新增的管理者可由另一位管理者刪除；
- 新增帳號缺少 PIN 或密碼時會被拒絕；非內建 admin 的帳號可切換三種角色；
- 照顧者登入後立即套用帳號預設語言；
- 未填報提醒的四個時段可分別啟用或關閉；
- 兩位長輩設定不同健康數據預設值後，前台切換不會互相帶入；
- 照片管理與異常狀態可開啟及篩選；
- 舊日期缺漏照片顯示「日期未記錄」；
- 原有餐飲、用藥、健康、飲水、排便、照片及操作紀錄仍存在。

## 十二、回復

若必須回復：

1. 停止 1.3.2；
2. 移走目前資料目錄；
3. 還原升級前的完整備份；
4. 使用與該備份相同的舊版程式啟動；
5. 抽查登入、資料庫及照片。

不要將已由新版服務寫入中的資料庫同時交給舊版程式繼續寫入。
