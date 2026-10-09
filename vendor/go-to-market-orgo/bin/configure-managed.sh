#!/usr/bin/env bash
# Reconcile security, A2A, factory, Honcho, and Latitude on a running container.
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"
DC=(docker compose --env-file .env)

h() { "${DC[@]}" exec -T hermes hermes "$@"; }
set_config() { h config set "$1" "$2" >/dev/null; }

set_config agent.bot_mode_protocol true
set_config agent.verify_on_stop true
set_config approvals.mode manual
set_config approvals.mcp_reload_confirm true
set_config approvals.destructive_slash_confirm true
set_config skills.write_approval true
set_config skills.guard_agent_created true
set_config tool_loop_guardrails.hard_stop_enabled true
set_config privacy.redact_pii true
set_config security.redact_secrets true
set_config gateway.multiplex_profiles true
set_config gateway.platforms.a2a.enabled true
set_config gateway.platforms.a2a.extra.port 9900
set_config gateway.platforms.a2a.extra.advertised_toolsets '["strategy","research","outbound","partnerships","revenue-operations"]'
set_config platform_toolsets.cli '["file","web","browser","memory","skills","todo","kanban","a2a","clarify","vision"]'
set_config platform_toolsets.slack '["file","web","browser","memory","skills","todo","kanban","a2a","clarify","vision"]'
set_config platform_toolsets.telegram '["file","web","browser","memory","skills","todo","kanban","a2a","clarify","vision"]'
set_config platform_toolsets.a2a '["session_search","memory","file","web","kanban"]'
set_config mcp_servers.agent-factory.command /opt/hermes/.venv/bin/python
set_config mcp_servers.agent-factory.args '["/opt/data/managed/services/agent_factory_mcp.py"]'
set_config mcp_servers.agent-factory.env '{"AI_GUY_FACTORY_STATE_DIR":"/opt/data/managed/state","AI_GUY_FACTORY_ASSETS_DIR":"/opt/data/managed","HERMES_HOME":"/opt/data"}'
set_config mcp_servers.agent-factory.trust trusted
set_config mcp_servers.agent-factory.enabled true

if grep -q '^HONCHO_API_KEY=..' .env; then
  set_config memory.provider honcho
  h honcho sync >/dev/null 2>&1 || true
fi

if grep -q '^LATITUDE_API_KEY=..' .env && grep -q '^LATITUDE_PROJECT_SLUG=..' .env; then
  h plugins enable latitude-observer >/dev/null
fi

# Composio now recommends the session-provided MCP URL. Prefer it, while
# retaining the documented v3.1 transport as a no-downtime migration path for
# installations that already have a legacy server ID.
if grep -q '^COMPOSIO_API_KEY=..' .env && grep -q '^COMPOSIO_MCP_URL=..' .env; then
  set_config mcp_servers.composio.url '${COMPOSIO_MCP_URL}'
  set_config mcp_servers.composio.headers.x-api-key '${COMPOSIO_API_KEY}'
  set_config mcp_servers.composio.trust untrusted
  set_config mcp_servers.composio.timeout 90
  set_config mcp_servers.composio.enabled true
elif grep -q '^COMPOSIO_API_KEY=..' .env \
  && grep -q '^COMPOSIO_USER_ID=..' .env \
  && grep -q '^COMPOSIO_MCP_SERVER_ID=..' .env; then
  set_config mcp_servers.composio.url 'https://backend.composio.dev/api/v3.1/mcp/${COMPOSIO_MCP_SERVER_ID}?user_id=${COMPOSIO_USER_ID}'
  set_config mcp_servers.composio.headers.x-api-key '${COMPOSIO_API_KEY}'
  set_config mcp_servers.composio.trust untrusted
  set_config mcp_servers.composio.timeout 90
  set_config mcp_servers.composio.enabled true
fi

if grep -q '^ENABLE_AGENT_BUNDLE=true$' .env; then
  echo "Agent Bundle remains blocked in this role. Use the Co-Founder review process for an exception." >&2
  exit 1
fi
