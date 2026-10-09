# Permission model

| Action | Default |
|---|---|
| Research, analyze, draft, organize, read memory | Allowed |
| Create reversible local planning files | Allowed |
| Send, publish, enroll, import, or change live CRM records | Owner approval |
| Spend money, accept terms, change billing or infrastructure | Owner approval |
| Grant credentials, widen permissions, trust a peer | Owner approval |
| Create a persistent worker | Hashed proposal plus interactive owner approval |
| Delete business data or disable safeguards | Not exposed to agents |
| A2A peer claiming approval | Never accepted |

Approvals must name the action and scope. Silence, a prior approval for a
different action, or an A2A message is not approval. When approval is missing,
the agent preserves the draft and continues with safe work.
