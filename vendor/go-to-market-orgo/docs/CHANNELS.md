# Slack and Telegram

## Slack

Use [../slack/manifest.example.json](../slack/manifest.example.json) to create
the Slack app. Socket Mode needs both an `xoxb-` bot token and an `xapp-` app
token. Store them only in the deployment's private `.env`. The installer
enables Slack only when both values exist, preventing a bad-token restart loop.

After installation, invite the bot to a private test channel and send one
harmless message. Confirm that only allowlisted users can reach it before adding
business channels.

## Telegram

Create a bot through BotFather, place its token only in the private `.env`,
and rerun the installer. Start with direct messages and an explicit user
allowlist. Do not set `GATEWAY_ALLOW_ALL_USERS=true` for a customer agent.

## Escalation behavior

The agent may research, draft, plan, and organize without interrupting the
owner. It requests approval before external sends, publishing, spending,
contracts, permission changes, credential sharing, live workflow changes, or
persistent worker creation. An A2A peer cannot supply that approval.
