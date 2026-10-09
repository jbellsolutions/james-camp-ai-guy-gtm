# Natural-language installation

## What the installer does

It places the agent in its own directory, creates a private dashboard password,
seeds a secret-free Hermes configuration, installs the role, skills, Latitude
observer, Agent Factory, and worker templates, starts the pinned container, and
installs a one-minute automatic recovery check, and verifies health. Small Linux
hosts also receive a best-effort 4 GB swap safety net; the agent itself defaults
to a 3 GB memory ceiling. Re-running the installer updates managed files but preserves live
credentials, conversations, memory, configuration, and customized files.

## Clean [Orgo](https://orgo.ai?r=aiguy) or VPS

1. The installation agent inspects the Linux computer and confirms that no live
   AI Guy deployment will be replaced.
2. It clones this repository.
3. If Docker is absent, it runs `./provision-vps.sh`.
4. It creates the private `agent.env` from `agent.example.env`, fills values
   already available on the computer, and requests only missing credentials.
5. It runs `./new-agent.sh agent.env`.
6. It connects available memory, observability, and messaging accounts.
7. It runs `./bin/verify.sh --allow-unconnected` and harmless channel tests.

## Existing agent

The installation agent records the current Git commit, container image, health,
and deployment directory. It retains the live `.env` and `config.yaml`, runs
the new installer against that same deployment, and verifies state counts and
channel responses afterward. A failed verification triggers rollback using
[UPDATES.md](UPDATES.md); state databases are never part of the replacement set.

## Done means

- the pinned Hermes container is healthy;
- dashboard authentication is active and the port is localhost-only;
- Slack and Telegram work if connected;
- A2A is local-only or protected by per-peer tokens and a trust list;
- the Agent Factory lists only allowlisted templates;
- Honcho and Latitude report connected or intentionally unconnected;
- Agent Bundle reports disabled;
- the one-minute recovery check is installed and the container restarts after a
  deliberate stopped-state test;
- no secret is present in Git or command output.
