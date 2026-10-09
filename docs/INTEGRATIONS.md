# Integration catalog and connection gates

| Component | Included route | Live gate |
|---|---|---|
| GitHub CLI | Target CLI/auth instructions; source lock | `gh auth status`; repo access; never reuse Justin’s token |
| Instantly | Bundled `skills/sales/instantly-*` plus scripts/references | API v2 read, paused synthetic staging, webhook/poll, stop-on-reply and thread send readback |
| Smartlead | `skills/smartlead-operations` | Current schema, scoped account/campaign, paused staging, reply payload and stop/readback tests |
| GHL Agent 4 | Bundled CLI/MCP public API source | Scoped Private Integration/OAuth for exact James location, reads, contact upsert, conversation, consented SMS and delivery/reply tests |
| Relationship graph | relcore standard-library engine | Synthetic CSV import, card/context brief, reply classification and graph links |
| Data Box | Optional pinned repo in source lock | Host/key/budget health probe, source provenance, small sample; not required |
| BrowserBox | Optional pinned repo in source lock | Browser service login, permitted source and serialized computer lease; never guaranteed unlimited scraping |
| Composio | Included CLI skill; optional auth/connection | `whoami`, chosen toolkit/account link, schema inspection, read probe; executor ownership remains unchanged |
| PlusVibe | Optional official docs capture/skill authoring | Owner selects service; verify plan/API and client workspace, official auth/endpoints and whether any MCP exists |
| Slack | Manifests, create/validate helper, Socket Mode | Owner workspace consent, bot/app tokens, owner Member-ID allowlist, real message/reply |
| Affiliate | Optional charter and selected source skills | Terms/taxonomy approved; existing card ownership and attribution source mapped |

Current official references checked October 9, 2026:

- [Instantly webhooks](https://help.instantly.ai/en/articles/6261906-webhooks): events are POST JSON; reply events are available. Configure provider-native auth supported by your account, or a secret ingress route plus reconciliation. Do not assume a signature/header exists without testing.
- [Smartlead API](https://helpcenter.smartlead.ai/en/articles/125-full-api-documentation): inspect current campaign/message-history/reply routes and webhook operations. API keys in URLs must be redacted from logs.
- [GHL send message](https://marketplace.gohighlevel.com/docs/2021-04-15/ghl/conversations/send-a-new-message/) and [conversation providers](https://marketplace.gohighlevel.com/docs/marketplace-modules/ConversationProviders/): sending and importing an inbound message are distinct. Do not mirror a message as a new outbound SMS.
- [GHL SMS guidance](https://help.gohighlevel.com/support/solutions/articles/155000000079): consent and opt-out behavior must be verified before SMS activation. This package’s conservative outreach hold is a policy, not a legal determination.
- [PlusVibe official API](https://developer.plusvibe.ai/): capture docs for the chosen workspace/plan; do not invent endpoint names or claim a verified MCP.
- [Slack manifests](https://docs.slack.dev/app-manifests/configuring-apps-with-app-manifests): manifest automation does not remove workspace OAuth/admin consent.

API/tool connections are optional until selected. Sourcing can work from uploads without any enrichment keys. Prefer scoped public GHL APIs and supported snapshots/UI for client workflows; bundled advanced internal-API utilities are not authorized for James’s location.

## Install GHL tools after selecting the connection

On the selected Linux host run `bash scripts/connect-ghl.sh /srv/james-gtm`. It copies the bundled tool source to private persistent state, creates its own venv inside the conversation container, installs source-declared dependencies plus the MCP transport, and registers the MCP only for conversation roles. Keep GHL_API_KEY and GHL_LOCATION_ID in the private conversation .env; restart after key changes. Do not put another client’s registry in this copy. This helper installs mechanics; location and SMS acceptance remain mandatory.

## Claude Code plugin

The repo includes a marketplace and plugin manifest. In Claude Code, add `jbellsolutions/james-camp-ai-guy-gtm` as a marketplace with `/plugin marketplace add`, then install `james-camp-ai-guy-gtm@james-camp-gtm` with `/plugin install`. Alternatively load the cloned folder with `--plugin-dir`. These workflows are documented in [Claude Code’s official plugin guide](https://code.claude.com/docs/en/plugins). Repository access must already be granted. Plugin skills guide installation and operations; enabling the plugin alone does not deploy runtimes or authorize outbound sends.

Optional source fetching: `python3 scripts/fetch-optional.py data-box --destination /srv/james-gtm/tools/data-box` (or browser-box). This checks out the locked commit, never executes remote installers or activates a service. Read source instructions, supply James’s keys privately and run the bounded source/health test before enabling. The included source skills supply tool guidance; they do not claim a connected service.

For a file-by-file dependency audit, see [Toolkit](TOOLKIT.md). Select accounts from [Services](SERVICES.md) and complete [Ready to run](READY-TO-RUN.md). CSO review mappings are covered in [CSO](CSO.md).
