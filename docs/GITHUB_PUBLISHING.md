# 發布至 GitHub

## 建立 repository

在 GitHub 建立空白 repository，不要預先產生 README、License 或 `.gitignore`，以避免第一次推送衝突。

## 本機推送

```bash
git init
git add -- .dockerignore .env.example .gitattributes .github .gitignore \
  CHANGELOG.md CODE_OF_CONDUCT.md CONTRIBUTING.md DISCLAIMER.md Dockerfile LICENSE \
  Makefile README.md README.en.md SECURITY.md VERSION app.py config.py docker-compose.yml \
  docker-entrypoint.sh docs fonts locales models.py pyproject.toml requirements-dev.txt \
  requirements.txt routes scripts security.py services static templates tests \
  translations.py uploads utils.py
git commit -m "Release CareLog 1.3.2"
git branch -M main
git remote add origin git@github.com:<YOUR_ACCOUNT>/<YOUR_REPOSITORY>.git
git push -u origin main
```

若改用 `git add .`，至少先執行 `git status --short`，確認 `.env`、`data/`、`carelog.db`、照片與字型沒有被納入。

## 建議的 GitHub 設定

- 啟用 Issues、Discussions 與 Private vulnerability reporting。
- 將 `main` 設為受保護分支，要求 CI 通過才可合併。
- 建立 `v1.3.2` tag 與 Release，附上 `CHANGELOG.md` 摘要。
- Repository 說明可使用：`Multilingual Flask home-care reporting and family dashboard platform.`
- Topics 建議：`flask`, `home-care`, `caregiver`, `health-dashboard`, `multilingual`, `sqlite`。
