# Infrastructure and eligible audience

Inventory actual domains, mailbox owners, provider, authentication, health and monitored reply channel. Read current provider guidance and DNS state. Verify SPF/DKIM/DMARC are configured as intended, check alignment and authentic sender identity, inspect bounce/complaint trends, unsubscribe/suppression and available capacity. Never report healthy infrastructure solely because an API accepted an upload.

Record verification provider/result/time and eligibility policy. Invalid, unverified, unknown or stale results are held; catch-all defaults to hold unless James adopts an explicit tested policy. Recheck suppression at staging and at dispatch. An import cannot restore an opt-out.

Mailbox ramp/warmup and sending limits are provider/account decisions requiring current evidence. James adopts caps, recipient-local windows and stop thresholds; do not ship invented universal limits. Prepare changes to DNS, domains, credentials or purchased capacity for authorized execution, with readback/rollback. No bought mailbox/domain outside budget.

Gate launch on current infrastructure snapshot, exact audience/copy review, observed reply path, stop-on-reply and authenticated event/reconciliation route. Monitor human replies, failures, complaints and suppressions; pause degraded campaigns with receipts. Fix infrastructure first, then audience/list, then offer, then copy.
