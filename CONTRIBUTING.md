# Contributing to CareLog

感謝協助改善居家照顧工具。提交內容時，請優先考量照顧者操作是否簡單、資料是否正確，以及家庭健康資料是否受到妥善保護。

## 開發環境

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
CARELOG_START_SCHEDULER=0 flask --app app init-db
python app.py
```

## 修改前後的檢查

```bash
python -m compileall -q .
python scripts/check_translations.py
python scripts/static_check.py
pytest
```

也可以執行：

```bash
make check
```

## Pull request 原則

1. 一個 PR 聚焦一項問題，避免同時混入無關格式化。
2. 新功能必須補測試；修正錯誤時，應先加入能重現問題的測試。
3. 涉及資料表變更時，必須說明舊資料庫如何升級與回復。
4. 新增翻譯鍵時，要同步更新所有 `locales/*.json`。
5. 不得提交真實健康資料、照片、SMTP 密碼、`.env` 或資料庫。
6. 使用者介面應兼顧手機、低數位熟悉度與多語照顧者。

## 提交訊息建議

使用清楚的動詞開頭，例如：

- `feat: add caregiver dashboard access`
- `fix: preserve records when deleting a user`
- `docs: expand NAS deployment guide`
- `test: cover report min and max statistics`

## 回報安全問題

請勿公開建立包含弱點細節的 Issue；依照 [SECURITY.md](SECURITY.md) 使用 GitHub 私密弱點通報管道。
