# Safe updates

## Release rule

An update is staged before it touches the live deployment. Record the current
repository commit, container image, container health, and state-file counts.
Run repository tests and static verification against the candidate. Only then
rerun `./new-agent.sh agent.env` against the existing deployment.

The installer owns the Compose file, helper scripts, role assets, worker
templates, policy, and Latitude observer. It never replaces the live `.env`,
`config.yaml`, databases, conversations, Honcho state, vault, or logs.
Managed files changed by the customer are detected by hash and preserved.

## Verification and rollback

After update, verify container health, pinned image, dashboard authentication,
channel responses, A2A Agent Card/auth rejection, Factory policy, Honcho status,
Latitude status, and state-file counts. Keep the prior repository checkout and
managed-file snapshot until those tests pass.

If any check fails, restore the prior Compose/helpers/managed files and
`config.yaml`, recreate the prior pinned container, and verify again. Do not
roll back or replace state databases; the update contract never edits them.

The fleet release identity is [../fleet/release.json](../fleet/release.json).
