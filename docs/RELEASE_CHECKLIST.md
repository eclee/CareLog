# GitHub 發布檢查表

## 程式與測試

- [ ] `python -m compileall -q .`
- [ ] `python scripts/check_translations.py`
- [ ] `python scripts/static_check.py`
- [ ] `python -m pytest`
- [ ] 以管理者、家屬、照顧者三種角色實際登入
- [ ] 驗證帳號刪除、自我刪除阻擋與歷史紀錄保留
- [ ] 驗證儀表板與報表的平均、最低、最高
- [ ] 驗證五種語言與手機窄螢幕導覽列

## 隱私與安全

- [ ] 未提交 `.env`、資料庫、照片、字型、備份或 log
- [ ] 範例資料均為虛構資料
- [ ] `CARELOG_SECRET` 不在程式碼或文件中出現真實值
- [ ] 初始管理者密碼與示範 PIN 已在文件中標示必須更換
- [ ] 安全弱點通報方式已記載於 `SECURITY.md`

## 文件與版本

- [ ] `VERSION`、`pyproject.toml`、Docker image tag 與 `CHANGELOG.md` 版本一致
- [ ] README 的本機連結均可開啟
- [ ] `LICENSE`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md` 與 `DISCLAIMER.md` 已納入
- [ ] 建立 `v1.1.0` tag，Release 說明引用 `CHANGELOG.md`

## 發布後

- [ ] GitHub Actions 全部通過
- [ ] 從乾淨目錄重新 clone 並依 README 完成一次安裝
- [ ] Docker Compose 可啟動，且 `data/` 重建容器後仍保留
- [ ] Repository 的 Issues 與 Private vulnerability reporting 設定完成
