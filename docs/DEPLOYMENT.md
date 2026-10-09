# Orgo and DigitalOcean deployment

Both routes use the same pinned Linux Docker runtime. James chooses the computer/host before provisioning. A GUI is useful for browser-only accounts; API, verification, copy and CRM tasks can run headlessly. Budget four leased screens maximum; a profile does not require its own screen.

## Target checks

Inspect `uname`, free disk/RAM, Docker/Compose, existing services and occupied ports. Default two stacks allocate up to 3 GB/2 CPUs each; plan host capacity for both plus the OS/browser. Orgo 8 GB or larger is a starting capacity assumption, to verify under actual browser load. Never resize/buy silently. DigitalOcean requires owner project/region/SSH and current priced droplet selection. Restrict SSH/firewall; keep dashboards and A2A on loopback; use authenticated tunnel access.

## Install

Clone this repository on the target with `gh repo clone jbellsolutions/james-camp-ai-guy-gtm`. Run package checks, then prepare:

```bash
python3 scripts/install.py --mode both --prepare-only --state-root /srv/james-gtm
```

The private files are `/srv/james-gtm/cold-email/agent.env` and `/srv/james-gtm/conversations/agent.env`. The installer chooses separate names, ports (18789/18790), A2A ports (9900/9901), state and vault folders. Enter model/selected channel keys privately. `agent.env` is shell-sourceable by the source installer; it must be owner-controlled and safely quoted. Never load an untrusted uploaded env file.

Review the bundled `vendor/go-to-market-orgo/provision-vps.sh` before using it on a clean authorized Linux host. Existing Docker installs need no reprovisioning. Then:

```bash
python3 scripts/install.py --mode both --deploy --state-root /srv/james-gtm
```

The source runtime installer is pinned in this repo and preserves existing state. Client overlay disables generic factory/A2A/auto-decomposition and uses explicit profile homes. A deployment conflict is reported instead of overwriting customization. Profiles are independent HERMES_HOME directories. Run a role through `scripts/run-profile.sh STATE_ROOT INSTALL PROFILE PROMPT_FILE`. Profile config has Slack disabled; only the root supervisors receive Slack, preventing several agents answering the same channel.

Optional affiliate profile:

```bash
python3 scripts/install.py --mode conversations --affiliate --deploy --state-root /srv/james-gtm
```

Enablement adds assets only; it grants no permission to send or set terms. Check deployment ownership/permissions and run harmless inference before business work. The package scripts require Python 3.10+; source runtime dependencies are installed in the container, not the Mac.

## Connect tools

Mount/install the bundle’s workflow tools, relcore and GHL MCP on the selected target. Configure per-profile MCP only for assigned roles; `docs/INTEGRATIONS.md` explains the selected source tool contracts. GHL dependencies install into a separate venv from bundled setup.py. Do not add user-wide MCP entries that leak client credentials. Provider API keys go to narrowly scoped adapters or credential stores; all profiles in one container share an OS trust boundary.

## Health and recovery

Run `scripts/verify-runtime.sh RUNTIME_DIR`, harmless inference per selected profile, root Slack smoke, then live acceptance. `docker compose` in each runtime directory controls that stack. Before updates, stop ingress, back up both state trees privately, record image/commit/config, and retain a restore point. Reapply assets without overwriting edits; resolve drift before claiming an upgrade. Restore version plus databases together, reconcile queued external outcomes, then resume ingress. Never wipe a state volume.

Emergency stop: `bash scripts/emergency-stop.sh /srv/james-gtm`; disable sequencer/GHL sending workflows and stop execution workers. The ledger honors this for intake/task retrieval, but an independent provider campaign must be paused at its provider too. Research/drafting may continue. Only James can authorize recovery after reconciliation.
