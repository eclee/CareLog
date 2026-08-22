# Changelog

All notable changes to CareLog are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-08-22

### Added

- Administrator parameter page for configurable water shortcut values, new-elder
  defaults, dashboard period, image limits, and abnormal-event rules.
- Medication reference photos captured from the camera or uploaded from a
  device, with primary-image selection and caregiver-side display.
- Structured media storage by elder, record date, record type, and record ID,
  including normalized JPEG files, thumbnails, checksums, dimensions, and
  protected ID-based media URLs.
- Medication submission groups so evidence photos belong to the complete
  medication entry rather than only its first medication row.
- Filterable, paginated audit log by user, role, action, record type, elder,
  keyword, exact date, or date range.
- Administrator media library with gallery/grouped views and filters for elder,
  use, record type, record ID, uploader, abnormal linkage, and date.
- Persistent abnormal events for vital signs, missed medication, abnormal bowel
  types, selected meal-intake states, and optional daily low water intake.
- Abnormal-event workflow with severity, pending/tracking/resolved/dismissed
  states, handling notes, source records, images, and audit history.
- Commands for database upgrades, legacy media migration, and historical
  abnormal-event rebuilding.

### Changed

- Account deletion is now a soft deletion: login credentials are removed and
  the account is hidden, while historical identity and care-record attribution
  remain intact.
- User-management typography is reduced by two visual steps without affecting
  caregiver pages or other admin screens.
- Vital alert persistence is separated from email delivery, so an email failure
  cannot erase the abnormal event.
- Vital thresholds moved to the parameter page; notification settings now focus
  on delivery and scheduling.
- Dashboards include average, minimum, maximum, and count; HTML/PDF reports
  additionally show when minimum and maximum vital values occurred.

### Fixed

- Legacy PNG and other image formats are actually decoded and converted to JPEG
  during migration instead of only receiving a new extension.
- Partial image files are removed when an upload fails.
- Deleted photos are excluded from the abnormal-event photo filter.
- Abnormal follow-up image limits no longer count source evidence or medication
  reference photos.

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
