# CareLog Home-Care Reporting and Management Platform

[繁體中文](README.md)

CareLog is a Flask platform for a single household or small home-care setting. Caregivers can report meals, medication, vital signs, water intake, bowel movements, and supporting photos from a phone. Family members and caregivers can review trends, while administrators manage elders, medication plans, accounts, parameters, notifications, media, abnormal events, and reports.

> CareLog is a communication aid, not a medical device, diagnostic service, medication instruction system, emergency monitor, or guaranteed alert channel. Read [DISCLAIMER.md](DISCLAIMER.md) and [SECURITY.md](SECURITY.md) before using real data.

## Highlights in 1.2.0

- Administrator parameters for water shortcut values, water-entry limits, new-elder defaults, dashboard period, image limits, and abnormal-event rules.
- Medication reference photos captured from a camera or uploaded from a device, with primary-image selection and caregiver-side display.
- Structured media storage by elder, date, record type, and record ID, with JPEG normalization, thumbnails, checksums, metadata, and protected ID-based URLs.
- Medication-submission groups so one evidence image can represent the complete multi-medication entry.
- Filterable, paginated audit records by user, role, action, type, elder, keyword, exact date, or date range.
- Administrator media library with gallery and grouped views.
- Persistent abnormal events for vital signs, medication not given, selected meal and bowel conditions, and optional daily low water intake.
- Pending, tracking, resolved, and dismissed workflows with handling notes, source records, and related images.
- Soft account deletion that removes credentials while retaining historical identity and care-record attribution.
- Average, minimum, maximum, occurrence time, and count summaries in dashboards and reports.
- Traditional Chinese, Indonesian, Vietnamese, Filipino, and Thai caregiver interfaces.

## Roles

| Role | Sign-in | Access |
|---|---|---|
| Caregiver `worker` | Name and PIN | Care entry, dashboard, photos, language switch |
| Family `family` | Username and password | Dashboard, photos, language switch |
| Administrator `admin` | Username and password | Full admin console, care entry, dashboard, media and abnormal-event handling |

CareLog currently assumes a single household. Tenant isolation and per-user elder authorization are not included.

## Quick start with Python

Requires Python 3.10–3.13.

```bash
cd CareLog-1.2.0
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

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

Open `http://127.0.0.1:8501`. The database, settings, and uploads are stored in `data/`.

## Upgrade from 1.1.0

Stop the service and back up the database and upload directory first. Then run:

```bash
CARELOG_START_SCHEDULER=0 flask --app app upgrade-db
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --dry-run
CARELOG_START_SCHEDULER=0 flask --app app media-migrate --apply
```

Historical abnormal events can optionally be rebuilt with the current rules:

```bash
CARELOG_START_SCHEDULER=0 flask --app app rebuild-abnormal-events \
  --from-date 2026-01-01 --to-date 2026-08-22
```

See [docs/UPGRADE.md](docs/UPGRADE.md) for limitations and verification steps.

## Checks

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q .
python scripts/check_translations.py
python scripts/static_check.py
python -m pytest
```

## Documentation

- [Build, deployment, backup, and operations](docs/BUILD_AND_DEPLOY.md)
- [Upgrade from 1.1.0](docs/UPGRADE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Adding languages](docs/LOCALIZATION.md)
- [Publishing to GitHub](docs/GITHUB_PUBLISHING.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

[MIT License](LICENSE)
