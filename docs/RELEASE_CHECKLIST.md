# CareLog 1.2.0 GitHub 發布檢查表

## 程式與測試

- [ ] `python -m compileall -q .`
- [ ] `python scripts/check_translations.py`
- [ ] `python scripts/static_check.py`
- [ ] `python -m pytest`
- [ ] 以管理者、家屬、照顧者三種角色實際登入
- [ ] 驗證三個喝水快捷值與新增長輩預設值
- [ ] 驗證藥物拍照／上傳、主圖、前台顯示與刪除
- [ ] 驗證新填報照片的結構化路徑、縮圖與圖片 ID 存取
- [ ] 驗證帳號停用式刪除、自我刪除阻擋及歷史身分保留
- [ ] 驗證操作紀錄的使用者、角色、類型、單日及期間篩選
- [ ] 驗證照片庫的長輩、用途、紀錄 ID、日期及異常篩選
- [ ] 驗證生命徵象、未給藥、排便與進食異常事件
- [ ] 驗證異常事件狀態、處理說明、來源照片及操作紀錄
- [ ] 驗證儀表板與報表的平均、最低、最高、次數與日期
- [ ] 驗證五種語言與手機窄螢幕導覽列

## 升級與資料

- [ ] 以 1.1.0 測試資料庫執行 `flask --app app upgrade-db`
- [ ] 連續執行兩次升級命令，第二次不重複修改
- [ ] 執行 `media-migrate --dry-run`，確認統計合理
- [ ] 執行 `media-migrate --apply`，抽查 JPEG、縮圖與雜湊
- [ ] 再次執行媒體搬移，不重複搬動新路徑圖片
- [ ] 視需要執行指定期間的歷史異常重建
- [ ] 完成升級前備份與實際還原演練

## 隱私與安全

- [ ] 未提交 `.env`、資料庫、`data/`、照片、字型、備份或 log
- [ ] 未提交 `.venv`、`__pycache__`、`.pytest_cache` 或本機 IDE 設定
- [ ] 範例資料均為虛構資料
- [ ] `CARELOG_SECRET` 不在程式碼或文件中出現真實值
- [ ] 初始管理者密碼與示範 PIN 已標示必須更換
- [ ] 圖片只能由登入者透過 ID 路由取得，不暴露實體路徑
- [ ] 敏感資料不出現在圖片檔名、稽核日誌或 Git 歷史
- [ ] 安全弱點通報方式已記載於 `SECURITY.md`

## 文件與版本

- [ ] `VERSION` 為 `1.2.0`
- [ ] `pyproject.toml` 版本為 `1.2.0`
- [ ] Docker image tag 為 `carelog:1.2.0`
- [ ] `CHANGELOG.md` 有 `1.2.0` 與發布日期
- [ ] README 的本機連結均可開啟
- [ ] `README.md`、`README.en.md`、架構、建置及升級文件同步
- [ ] `LICENSE`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md` 與 `DISCLAIMER.md` 已納入
- [ ] 建立 `v1.2.0` tag，Release 說明引用 `CHANGELOG.md`

## 發布後

- [ ] GitHub Actions 全部通過
- [ ] 從乾淨目錄重新 clone 並依 README 完成一次安裝
- [ ] Docker Compose 可啟動，且重建容器後 `data/` 仍保留
- [ ] 從 1.1.0 備份完成一次實際升級
- [ ] Repository 的 Issues 與 Private vulnerability reporting 設定完成
