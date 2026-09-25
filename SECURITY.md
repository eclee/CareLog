# Security Policy

CareLog stores health observations, care notes, and potentially sensitive
photos. Treat every deployment as a system containing private personal data.

## Supported versions

| Version | Security updates |
|---|---|
| 1.3.x | Yes |
| 1.2.x | Best effort |
| 1.1.x | Best effort |
| Earlier | No |

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting or a repository Security
Advisory when available. Do not post credentials, personal data, proof-of-
concept exploit details, or identifiable care records in a public Issue.

Include:

- affected version and deployment method;
- reproducible steps using synthetic data;
- expected and observed behavior;
- potential impact;
- a proposed mitigation, if known.

## Deployment baseline

Before using real data:

- replace the default administrator password and all example PINs;
- set a unique `CARELOG_SECRET` of at least 32 random bytes;
- place the service behind HTTPS or a private VPN;
- restrict filesystem and backup access;
- keep Python dependencies and the host OS updated;
- test database and photo restoration;
- do not expose the Flask development server directly to the Internet.

This repository is a home-care coordination tool, not a certified medical
device or emergency alert service.

## Current security boundaries

CareLog 1.4 includes session-based CSRF protection, role and elder access
checks, protected media URLs, hashed caregiver PINs, persistent login attempt
limits, and audit and abnormal-event records. It remains a single-household
tool. Four-digit PINs are weak even when hashed; change example credentials,
use a private VPN or HTTPS reverse proxy, and never treat Email as an emergency
notification channel. The login limit uses the connection's remote IP; only
configure forwarded IP handling for a proxy you control.
