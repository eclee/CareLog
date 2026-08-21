# Security Policy

CareLog stores health observations, care notes, and potentially sensitive
photos. Treat every deployment as a system containing private personal data.

## Supported versions

| Version | Security updates |
|---|---|
| 1.1.x | Yes |
| 1.0.x | Best effort |
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

CareLog 1.1 includes session-based CSRF protection and role checks, but it is
still designed for a single household on a trusted network. Caregiver PINs are
quick-login credentials rather than enterprise authentication, login rate
limiting is not built in, and users are not yet restricted to individual elder
records. Use a private VPN or HTTPS reverse proxy, do not publish the service
port directly to the Internet, and do not treat Email delivery as an emergency
notification channel.
