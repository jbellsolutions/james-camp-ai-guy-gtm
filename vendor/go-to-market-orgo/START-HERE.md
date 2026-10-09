# Start here: Go-To-Market for [Orgo](https://orgo.ai?r=aiguy)

> **[Orgo](https://orgo.ai?r=aiguy) partner offer:** Get 25% off your first three months on a monthly plan or your first year on a yearly plan. Add-ons are not discounted.

This repository is the complete, standalone Go-To-Market for [Orgo](https://orgo.ai?r=aiguy) agent.
It can run on an [Orgo](https://orgo.ai?r=aiguy) computer, DigitalOcean VPS, or another Ubuntu Docker host.

## If you are the installation agent

1. Read [AGENTS.md](AGENTS.md), then inspect the machine without changing it.
2. Identify any existing deployment, its private `.env`, Docker volume/state,
   channel connections, and the last healthy commit.
3. On a clean machine run `./provision-vps.sh`. On an existing machine, do not
   reinstall Docker or replace live data.
4. Prepare `agent.env` from `agent.example.env`. Reuse secrets already stored
   on the computer; never print or commit them.
5. Run `./new-agent.sh agent.env`. It is idempotent and preserves existing
   `.env`, `config.yaml`, state databases, Honcho data, and customized files.
6. Connect available Honcho and Latitude accounts with
   `./bin/connect-stack.sh`. Latitude starts metadata-only.
7. Connect Slack and/or Telegram according to [docs/CHANNELS.md](docs/CHANNELS.md).
8. Pair trusted agents with [docs/A2A.md](docs/A2A.md). Do not expose A2A before
   per-peer tokens and a trust allowlist exist.
9. Run `./bin/verify.sh --allow-unconnected`, then one harmless message through
   each connected channel.
10. Report the running version, connections, private URL, health evidence,
    preserved data, and rollback commit.

Stop and ask for one missing secret or account authorization only when the
machine does not already have it. Never ask the owner to run terminal commands.
