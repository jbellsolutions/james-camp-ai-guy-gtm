# Troubleshooting

Start with `./bin/verify.sh --allow-unconnected`. It checks the pinned image,
container health, approval mode, A2A, and Agent Factory without showing secrets.

## Container does not become healthy

Confirm the private `.env` has a real Fireworks key and a generated dashboard
password. Run `docker compose --env-file .env config --quiet`, then inspect the
Hermes logs. Current releases must use the upstream supervised entrypoint; remove
any legacy `entrypoint: /init-chown.sh`, `init: true`, or
`/start-hermes.sh` override from an older deployment.

## Slack or Telegram does not answer

A channel is enabled only when its required token set existed during first
configuration. Verify the token in the private `.env`, verify the platform
setting through Hermes, and recreate the container. Slack needs both bot and app
tokens for Socket Mode. Keep the gateway private and test with one allowlisted
user before widening access.

## Dashboard returns 401

This is expected until the generated basic-auth username and password are used.
Retrieve them from the mode-600 deployment `.env` without copying them into
chat or logs. The host port should remain bound to `127.0.0.1`.

## A2A peer cannot connect

Check that each side swapped the correct per-peer token, the receiving side
trusts the authenticated peer name, and the Agent Card advertises a routable
private URL. A remote bind without a token or trusted-peer list is intentionally
rejected. Review the A2A audit log for the status without exposing tokens.

If the Agent Card was working and then disappears, check the container's actual
run state—not only its last health value. An exited container can retain a stale
`unhealthy` health result. Confirm that the current user's crontab contains the
deployment's `bin/watchdog.sh`, run the watchdog once, and repeat the Agent Card
test. On a small host, also confirm that the configured memory ceiling is 3 GB
and that swap is active when the host supports it.

## Honcho or Latitude is absent

Run `./bin/connect-stack.sh --status`. Honcho activates when its key exists and
the memory provider is set to `honcho`. Latitude requires both a project key and
slug plus the enabled observer. Their outage must not stop the core agent.

## An update fails

Do not touch state databases. Restore only the previous Compose file, helper
scripts, managed assets, and `config.yaml`; then recreate the prior pinned image
and rerun verification. Fleet-managed updates create this rollback snapshot
before installation.
