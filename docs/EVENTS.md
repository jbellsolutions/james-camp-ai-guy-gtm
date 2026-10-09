# Durable reply handoffs

The included `workflow.py` stores normalized inbound events and tasks in a private SQLite ledger. It accepts one canonical envelope, deduplicates by client/provider/account/event ID, and queues independent stop/suppression, reply and CRM tasks. It does not claim a provider stop occurred until the Sequencer acknowledges the task with its actual receipt. Stop/suppression tasks are retrieved first.

`python3 scripts/workflow.py --db PRIVATE_DB ingest EVENT.json` commits before acknowledging ingress. `tasks --owner gtm-sequencer` previews work; `claim --owner gtm-sequencer` atomically reserves one task for its sole executor; `ack TASK_ID RECEIPT.json` requires a real external receipt. An ambiguous outcome uses `hold TASK_ID`, and the owning operator reconciles before resuming. `retry TASK_ID` is allowed only after reconciliation determines it was not accepted. No automatic provider write retry.

Normalized event fields:

```json
{"client":"james-camp","provider":"instantly","account":"james-account","event_id":"provider-message-id","channel":"email","contact":"alex@example.com","thread_id":"provider-thread-id","campaign_id":"provider-campaign-id","occurred_at":"2026-10-09T12:00:00Z","kind":"reply","text":"Could you explain how this works?"}
```

Also support `unsubscribe`/`complaint`/`wrong_number` kinds. Explicit opt-out/complaint overrides the model. The keyword floor holds obvious stop phrases even when kind is reply. Imported email/phone addresses are not canonical merges; Agent 4 resolves them against CRM. Out-of-order events retain timestamps; refresh the current provider thread before acting.

## Authenticated bridge

`python3 scripts/intake.py --db PRIVATE_DB --port 8765` listens on loopback. Read `GTM_INGRESS_TOKEN` from private environment. An authorized normalizing adapter posts `/events` with `Authorization: Bearer <token>`; max body 256 KiB. This is an internal normalized bridge, not an assertion that every provider supports this header. Verify each provider’s actual webhook delivery, authentication and retry behavior; terminate public TLS at a reviewed ingress adapter that validates provider auth/secret route, fetches source thread and normalizes to this envelope. Do not publish the loopback service naked.

Use provider-native webhook when verified; otherwise poll/reconcile unread/latest messages with a stored watermark and overlap for late events. Wakes feed Reply Agent / Agent 4. The installation agent configures the actual adapter against the connected account; completion is blocked until a real inbound test and duplicate replay pass. These adapters are connection-specific and are not preconfigured for James.

On CRM failure, keep the local task pending, honor provider sequence stop/suppression first, expose lag in the daily report. Do not retry unknown sends. On ingress downtime, reconcile from the provider using last committed watermark. Archive raw payload privately if needed, redact logs and never commit them.

Claimed tasks do not expire into automatic retries: a dead worker may already have written externally. Reconcile before hold/retry. All senders recheck current thread/suppression just before dispatch; a task claim is not send permission. Use one authorized worker per profile and keep release scope separate from task reservation.
