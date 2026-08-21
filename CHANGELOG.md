# Changelog

All notable changes to CareLog are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-08-21

### Added

- Administrator account deletion with safeguards against deleting the current
  account or the final active administrator.
- Persistent role-aware top navigation across admin, dashboard, care-entry,
  and photo pages.
- Average, minimum, maximum, and sample-count summaries for health metrics.
- Minimum and maximum daily water intake in dashboards and email/PDF reports.
- Vietnamese, Filipino, and Thai interfaces in addition to Traditional Chinese
  and Indonesian.
- Localized abnormal-vital warnings for caregivers in all five interface
  languages.
- Auto-discovered JSON locale architecture for future languages.
- Caregiver access to the family health dashboard and photo evidence pages.
- Default elder birthday of `1940-01-01` in both the form and server-side model.
- Automated tests, translation validation, GitHub Actions CI, issue templates,
  contribution guidelines, security policy, and deployment documentation.

### Changed

- Report PDF output now follows the selected report sections.
- Variable CJK fonts are converted correctly before PDF generation.
- Waitress deployment uses the Flask application factory without creating a
  duplicate scheduler instance.
- Deleted-account historical records remain available, with their creator
  attribution cleared to preserve referential integrity.

### Fixed

- Disabled elders cannot be queried from the dashboard data endpoint.
- Photo upload failures are logged instead of being silently discarded.

## [1.0.0] - 2026-08-01

- Initial home-care reporting MVP.
