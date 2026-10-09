# Slack self-install and owner consent

Two independent Socket Mode apps are provided in slack/cold-email.json and slack/conversations.json. Keep separate app/bot tokens so one root supervisor owns each conversation. Specialists have Slack disabled. There are no placeholder public URLs or unsafe slash commands in these manifests.

The installer performs manifest preparation, validation and creation where authorized. Read [official manifest setup](https://docs.slack.dev/app-manifests/configuring-apps-with-app-manifests) and [create API](https://docs.slack.dev/reference/methods/apps.manifest.create/). With a private workspace app-configuration token, run:

```bash
python3 scripts/slack-app.py slack/cold-email.json --create --output /srv/james-gtm/private/slack-email-app.json
```

SLACK_CONFIGURATION_TOKEN is supplied by private environment, never a command argument. Creation responses include client secrets; the helper writes them only to a new chmod-600 private receipt, reports app ID and requires owner consent. Unknown creation outcome must be reconciled in Slack’s app list before retrying. Existing receipt prevents blind duplication.

If no configuration token exists, the setup agent opens Slack’s app-manifest UI, imports the selected manifest, and guides the owner through workspace authorization. Owner/admin authorization cannot be silently self-granted. Create an app-level token with connections:write, install/authorize the bot, privately set SLACK_APP_TOKEN and SLACK_BOT_TOKEN, configure SLACK_ALLOWED_USERS with James’s Member ID(s), and choose a home channel. Invite the bot there. Never allow every user by default.

Rerun deployment only after correctly updating the live private .env as well as its source agent.env; source installer preserves existing .env. Test a designated harmless DM/mention and its reply. Verify unauthorized users cannot invoke it. Channel event subscriptions can be added if needed after verifying exact Hermes routing and scope. No live Slack install is claimed by package preparation alone.
