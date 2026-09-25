# Changelog

All notable changes to CareLog are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [1.4.0] - 2026-09-25

### Added

- Two-decimal weight input and display, inclusive custom dashboard dates, fluid composition and seven Bristol chart series.
- User-to-elder access grants, hashed caregiver PINs, persistent login attempt limits and medication schedule snapshots.
- Explicit schema-v4 upgrade gate, standalone backup helper, migration guide, environment sample, ignore rules and CI checks.

### Changed

- Dashboard, reports and optional low-fluid alerts share the water-plus-known-supplement total; unquantified supplements remain unknown.
- Planned medication adherence starts with the first known version; reported-medication rate remains separate.

## [1.3.2] - 2026-08-22

### Changed

- Every newly created active account must have both a 4–16 digit PIN and a
  password. Editing preserves existing credentials when fields are left blank,
  but legacy accounts missing either credential must add the missing value.
- Only the built-in account named `admin` has an immutable role. Every other
  account, including administrators created later, can be reassigned among
  administrator, family, and caregiver roles.
- Fresh installations now create the built-in administrator with both the
  initial password `care1234` and initial PIN `1234`; both must be changed
  immediately. Demo accounts also receive both credential types.

### Fixed

- Gmail app passwords copied from Google's grouped display no longer fail with
  an ASCII codec error when they contain U+00A0 no-break spaces, U+202F narrow
  no-break spaces, ordinary spaces, or zero-width format characters. SMTP
  usernames and recipient addresses are normalized and validated as well.
- Notification settings normalize copy/paste artifacts before saving, while the
  mail sender also normalizes previously stored values so existing settings do
  not need to be re-entered.
- Added regression tests for SMTP normalization, mandatory dual credentials,
  built-in administrator role protection, and role changes for all other
  accounts.

## [1.3.1] - 2026-08-22

### Changed

- Only the built-in account whose username is exactly `admin` is undeletable.
  Administrators created later can be soft-deleted by another administrator;
  the currently signed-in account still cannot delete itself.
- PIN and password are now independent credentials. Administrators and family
  accounts can store and change a PIN, while their normal sign-in method remains
  username and password.
- The caregiver interface now treats the account's saved language as
  authoritative immediately after sign-in.
- Unsubmitted meal reminders now have independent switches for morning, noon,
  evening, and bedtime in addition to the master reminder switch.

### Fixed

- Family accounts can be created reliably with an explicit password and an
  optional PIN; the form now makes role-specific requirements clear.
- Numeric filter selections in the administrator photo library, abnormal-event
  list, audit log, elder profiles, and per-elder parameters no longer raise a
  Jinja `UndefinedError`. The previous templates referenced Python's `int`
  global, which Jinja does not expose, so a filter page could open normally but
  fail only after a numeric selection was submitted. This defect was independent
  of the SQLite database version.
- Added regression coverage for integer-valued filters, built-in administrator
  protection, later-administrator deletion, family creation, all-role PIN
  editing, saved-language login, and per-timeslot reminder switches.

## [1.3.0] - 2026-08-22

### Added

- Expanded elder medical profile fields: gender, ABO/Rh blood type, height,
  contact details, allergies, chronic conditions, usual hospital/clinician, and
  emergency contacts.
- Per-elder vital-entry defaults for weight, systolic pressure, diastolic
  pressure, pulse, and SpO2, stored in the extensible `elder_settings` table.
- `flask --app app check-db` for explicit schema verification and Docker startup
  gating before Waitress begins serving requests.
- An actionable database-upgrade diagnostic page for missing SQLite tables or
  columns, including the configured database target and required command.
- A full 1.1.x-to-1.3.0 migration regression test covering the photo and
  abnormal-event search pages.

### Changed

- All administrator accounts are protected from deletion. Non-administrator
  accounts can now be edited, including username, display name, caregiver/family
  role, language, credentials, and active status.
- Elder forms are reorganized into basic, medical, and emergency-contact
  sections, with optional fields and data-minimization guidance.
- The vital-entry page pre-fills only the selected elder's configured defaults
  and explicitly warns that defaults are not measurements or medical limits.
- Database compatibility checks now validate the elder profile and per-elder
  settings schema in addition to the 1.2 media, audit, and abnormal-event schema.

### Fixed

- Legacy photos with both `record_date` and `uploaded_at` missing no longer
  trigger a 500 error in administrator or family photo views; they render as
  `日期未記錄` instead.
- Partially upgraded or incorrectly mounted databases no longer fail with only
  a generic Internal Server Error on photo/abnormal searches; the response now
  identifies the missing schema and directs the operator to `upgrade-db`.
- Duplicate report-setting metadata and a duplicate medication-plan redirect
  left from the prior integration were removed.
- Docker one-off commands such as `docker compose run ... flask --app app
  upgrade-db` are now forwarded by the entrypoint instead of unintentionally
  starting Waitress.

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
