# CareLog Home-Care Reporting and Management Platform

[繁體中文](README.md)

CareLog is a Flask-based platform for a single household or a small home-care setting. Caregivers can report meals, medication, vital signs, water intake, bowel movements, and supporting photos from a phone. Family members and caregivers can review trends, while administrators manage elders, medication plans, accounts, notifications, and reports.

> CareLog is a communication aid, not a medical device, diagnostic service, medication instruction system, emergency monitor, or guaranteed alert channel. Read [DISCLAIMER.md](DISCLAIMER.md) and [SECURITY.md](SECURITY.md) before using real data.

## Highlights in 1.1.0

- Safe account deletion while retaining historical care records.
- Persistent, role-aware navigation across admin, dashboard, care-entry, and photo pages.
- Average, minimum, maximum, timestamp, and sample-count summaries for numerical health data.
- Traditional Chinese, Indonesian, Vietnamese, Filipino, and Thai caregiver interfaces.
- Localized abnormal-vital warnings in all five interface languages.
- JSON locale auto-discovery: a new language can be added without modifying routes or templates.
- Dashboard and photo access for caregivers (`worker`).
- A default elder birthday of `1940-01-01`, editable during creation.
- GitHub Actions CI, tests, issue forms, contribution guidelines, security policy, deployment guide, and release checklist.

## Roles

| Role | Sign-in | Access |
|---|---|---|
| Caregiver `worker` | Name and PIN | Care entry, dashboard, photos, language switch |
| Family `family` | Username and password | Dashboard, photos, language switch |
| Administrator `admin` | Username and password | Admin console, care entry, dashboard, photos |

## Quick start with Python

Requires Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

# macOS / Linux: generate a random session signing key.
export CARELOG_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"

CARELOG_START_SCHEDULER=0 flask --app app init-db
python app.py
```

Open `http://127.0.0.1:8500` and sign in with the initial administrator account:

```text
username: admin
password: care1234
```

Change the initial password immediately and set a random `CARELOG_SECRET` before using real data.

## Quick start with Docker Compose

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Put the generated value in .env as CARELOG_SECRET.

docker compose up -d --build
```

Open `http://127.0.0.1:8501`. The database and uploads are stored in `data/`.

## Checks

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q .
python scripts/check_translations.py
python scripts/static_check.py
python -m pytest
```

## Documentation

- [Build, deployment, backup, and upgrade](docs/BUILD_AND_DEPLOY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Adding languages](docs/LOCALIZATION.md)
- [Publishing to GitHub](docs/GITHUB_PUBLISHING.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

[MIT License](LICENSE)
