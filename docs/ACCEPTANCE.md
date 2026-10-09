# Acceptance and completion evidence

## Package verification (no external accounts)

Run scripts/check.py, all tests, prepare both installs in a temporary directory, rerun and confirm edited assets/state are preserved. Replay duplicate email reply; verify stop and CRM tasks appear exactly once and in priority order. Replay STOP/wrong-number; verify suppression and no response task. Run relcore synthetic import and context generation. Confirm every profile has charter, identity and assigned skills; both installations use separate paths/ports. Record evidence in docs/VERIFICATION.md.

## Live installation gates (selected target/accounts)

- Pinned Docker image starts; client runtime health verification and harmless inference pass for each enabled profile. Check custom HERMES_HOME resolution and skill availability; incompatible runtime stops setup.
- Slack app installed by owner, Member-ID allowlist active, one authorized message/reply succeeds and an unauthorized user is denied.
- Uploaded-list path works without Data Box/API. If sourcing chosen, one small permitted source job has provenance and current cost receipt; email verification sample includes invalid/unknown/catch-all holds.
- Exact synthetic campaign stages paused; rendered audience/copy readback equals approved versions. Check authentication/DNS/reply path and adopted pause limits. Send only to James’s designated test address under test authorization.
- Real sequencer reply wakes the Reply Agent, stops that test sequence, classifies, acknowledges GHL handoff and cannot duplicate on replay. Test CRM failure/recovery with a test destination; stop still occurs.
- GHL scoped location read confirms identity. Synthetic/test contact upsert/readback, unique opportunity and note/next owner work. Provider-native AI/workflows do not duplicate responses.
- relcore context brief links person/company/campaign and preserves known answer/open loop. A changed brief invalidates stale drafts. Old client references are absent from current runtime identity.
- Real SMS to the owner-designated, consented test phone has provider receipt; inbound reply appears in CRM/context. STOP and wrong-number hold future proactive contact. Unknown consent/timezone does not send. An ambiguous result is reconciled, not replayed.
- Booking is verified in the calendar and CRM; no invented meeting/revenue. Affiliate mode, if selected, reuses cards and respects approved terms/payout boundaries.
- Emergency stop and backup/restore are verified using test state; no provider remains sending during stop. Document restart order and last good version.

Mark each selected integration LIVE only after its gate passes. Mark unselected services UNCONNECTED. Mark missing credentials/permissions or unsupported runtime behavior BLOCKED with next owner. Static tests do not justify a LIVE label. Preserve existing approved authorizations; this checklist does not require redundant permission for covered tests.
