# Security

Do not report security issues in a public issue with live credentials or
customer data. Rotate any credential that may have been exposed.

The default deployment binds the dashboard and A2A service to localhost.
Dashboard authentication is mandatory. A2A remote access requires both a bearer
token and an explicit trusted-peer list. The Docker socket is not mounted and
`no-new-privileges` is enabled.

Secrets belong only in the deployment's mode-600 `.env`, Hermes credential
stores, or provider OAuth stores. They must not be added to YAML templates,
prompts, skills, logs, telemetry, Git, A2A messages, or issue reports.

Latitude defaults to metadata-only. Agent Factory creation requires an
interactive, proposal-bound approval. Agent Bundle is disabled for this role.
See [docs/PERMISSIONS.md](docs/PERMISSIONS.md) for the action boundary.
