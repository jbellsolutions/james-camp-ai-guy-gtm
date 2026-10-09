---
name: smartlead-operations
description: Stage and operate Smartlead campaigns and email replies using current official API schemas, controlled release and receipt reconciliation.
---

This is a new operations skill; no preexisting Smartlead skill was located in the inspected sources. Read https://helpcenter.smartlead.ai/en/articles/125-full-api-documentation before implementing a call. Source docs describe API v1 at server.smartlead.ai, message-history and reply-email-thread routes; inspect exact current request/response fields and account permissions rather than guessing.

Select James’s client/campaign and private key. Redact API keys in query URLs and logs. Read account/campaign first; create/stage only under adopted scope, paused by default. Map eligible verified rows, exact rendered copy and sender/window/caps. Read back copy/list/settings; require editorial and infrastructure clearances plus release before launch. Never duplicate on ambiguous upload/launch/send; reconcile IDs and actual state.

Connect reply webhooks or supported polling with overlap/watermark. Fetch full thread. Stop sequence on reply, suppress opt-out immediately, normalize event to workflow ledger, hand off to Reply Agent/Agent 4. Sequencer remains sole email sender; native Smartlead AI may own replies only if the external reply sender is disabled and owner selects that mode. Reply drafts require current thread, approved facts and playbook. Test designated sample addresses, duplicate webhook replay, stop-on-reply, send readback and unknown outcome before live acceptance.
