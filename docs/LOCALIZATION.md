# CareLog 多語系擴充指南

## 現有語言

| 代碼 | 語言 |
|---|---|
| `zh` | 繁體中文 |
| `id` | Bahasa Indonesia |
| `vi` | Tiếng Việt |
| `fil` | Filipino |
| `th` | ไทย |

## JSON 結構

每個 `locales/<code>.json` 都包含 `_meta`：

```json
{
  "_meta": {
    "code": "ja",
    "name": "日語",
    "native_name": "日本語",
    "short": "日",
    "html_lang": "ja",
    "order": 60
  },
  "app_name": "...",
  "hello": "..."
}
```

欄位說明：

- `code`：必須與檔名相同；
- `name`：管理後台顯示名稱；
- `native_name`：語言選單顯示名稱；
- `short`：未來可用於窄版介面；
- `html_lang`：HTML `lang` 屬性；
- `order`：語言選單排序。

## 新增語言

```bash
cp locales/zh.json locales/ja.json
```

接著：

1. 修改 `_meta`；
2. 翻譯 `_meta` 以外的所有值；
3. 保留所有鍵名，不要自行新增或刪除；
4. 執行檢查並重新啟動 CareLog；語言清單會在應用程式啟動時載入。

```bash
python scripts/check_translations.py
python scripts/static_check.py
pytest
```

系統會自動發現新 JSON，不需要修改：

- `translations.py`；
- Flask route；
- Jinja template；
- 語言選單。

## 新增介面文字

需要新增翻譯鍵時：

1. 先在 `locales/zh.json` 新增語意明確的 snake_case 鍵；
2. 同步加入所有其他語言；
3. 使用 `t('key')`；含參數者使用 `tf('key', value=...)`；
4. 跑完整檢查。

參數範例：

```json
"recent_days": "近 {days} 天"
```

```jinja2
{{ tf('recent_days', days=30) }}
```

## 翻譯品質原則

- 優先使用照顧者在日常工作中熟悉的詞彙，不做逐字機器翻譯。
- 涉及用藥、血壓、血氧與排便型態時，應由母語使用者與照顧專業人員複核。
- 句子保持短、直接、可在手機上閱讀。
- 不要在翻譯值中放 HTML；排版由模板負責。
- 圖示只能輔助文字，不能成為唯一提示。
