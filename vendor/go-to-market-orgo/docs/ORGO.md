# [Orgo](https://orgo.ai?r=aiguy) deployment

Use one [Orgo](https://orgo.ai?r=aiguy) computer for this agent. Multiple worker profiles live inside the
same Hermes installation, so they do not require separate [Orgo](https://orgo.ai?r=aiguy) computers or
workspaces. Use A2A when this computer needs to speak to a different computer,
framework, or customer environment.

The installation agent should consult [Orgo](https://orgo.ai?r=aiguy)'s current documentation index at
<https://docs.orgo.ai/llms.txt> before making infrastructure changes. [Orgo](https://orgo.ai?r=aiguy)'s
current model is a workspace containing computers; the API supports start,
stop, restart, screenshots, terminal commands, and computer-control prompts.

## Safe deployment sequence

1. Select the existing customer workspace and intended computer. Do not create,
   resize, upgrade, or delete infrastructure unless the owner explicitly asks.
2. Start the computer if needed and record its ID and current health.
3. Install this repository through [INSTALLATION.md](INSTALLATION.md).
4. Keep dashboard and A2A ports private. Prefer the workspace's private network
   or a tailnet; never expose the dashboard directly to the public internet.
5. Connect Slack/Telegram from inside the agent; [Orgo](https://orgo.ai?r=aiguy) hosts the computer, while
   Hermes hosts the messaging gateway.
6. Record the repository commit, stack version, computer ID, and rollback point.

Stopping an [Orgo](https://orgo.ai?r=aiguy) computer stops replies and scheduled work until it starts
again. Persistent files remain on the computer, but an agent expected to answer
Slack or Telegram continuously must use an appropriate always-on/auto-stop
configuration.
