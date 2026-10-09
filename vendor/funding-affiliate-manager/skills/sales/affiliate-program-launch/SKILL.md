---
name: affiliate-program-launch
description: Launch and operate a governed affiliate program or affiliate company using repeatable strategy, partner, compliance, finance, technology, and operating artifacts. Use when starting a new affiliate program, onboarding an affiliate manager, or preparing governance-board materials.
---

# Affiliate Program Launch

## Purpose

Launch a focused, profitable, compliant affiliate program with explicit ownership, reliable attribution, controlled payouts, and a repeatable partner lifecycle. Start with one vertical, one primary geography, and one conversion type unless governance approves broader scope.

## Operating principles

1. Optimize for validated incremental contribution profit, not clicks or gross attributed revenue.
2. Treat advertisers and affiliates as two distinct customer groups.
3. Separate tracking, attribution, and settlement.
4. Use deterministic, versioned rules for payable commissions.
5. Keep immutable event history; correct with adjustment events rather than deletes.
6. Buy commodity infrastructure first; build proprietary margin, quality, reconciliation, and workflow intelligence.
7. Move fast on growth, slowly on trust, and make every dollar traceable.

## Required launch gates

### Gate 1: market viability
- One vertical, geography, conversion type, and ICP selected.
- 25–40 advertiser interviews and 40–60 affiliate interviews or equivalent evidence.
- 3–5 signed or committed advertiser pilots.
- 20–30 qualified prospective affiliates.
- Unit economics show a credible path to positive contribution margin.

### Gate 2: operational readiness
- Standard terms, traffic policy, disclosure rules, and approval matrix approved.
- Tracking, postbacks, conversion deduplication, and payout rules tested.
- Partner due diligence and risk tiers live.
- Finance reconciliation and payment controls documented.
- Incident, fraud, privacy, and escalation owners assigned.

### Gate 3: beta readiness
- 3–5 advertisers and 20–40 approved affiliates.
- Manual approval for partners, offers, and high-risk traffic.
- Daily anomaly monitoring and weekly reconciliation.
- No unresolved critical attribution or payment defects.

### Gate 4: scale readiness
- Repeat advertiser activity and multiple producing affiliates.
- Tracking accuracy at least 98% and payout accuracy at least 99% as initial targets.
- Fraud, invalid traffic, refunds, and disputes within approved thresholds.
- Documented SOPs and an owner for each critical metric.

## Core roles and accountability

- CEO/GM: strategy, capital, culture, executive relationships.
- Accountable Affiliate Executive: revenue, margin, risk, and board reporting.
- Head of Supply: advertiser acquisition, offer quality, commercial terms.
- Head of Demand: affiliate recruitment, activation, retention.
- Operations/Trust Lead: onboarding, support, fraud, compliance, payouts.
- Product/Engineering Lead: tracking, integrations, data, automation.
- Finance/Revenue Operations: reconciliation, forecasting, liabilities, payments.
- Legal/Privacy: contracts, disclosures, data use, regulated-market review.

One accountable owner must be named for revenue, contribution margin, tracking accuracy, payout accuracy, fraud loss, partner retention, advertiser retention, and compliance.

## Partner lifecycle

1. Prospecting
2. Application
3. Identity/KYC, sanctions, tax, beneficial-owner, and traffic-source review
4. Risk tier assignment
5. Contracting
6. Offer, placement, and creative approval
7. Technical onboarding
8. Activation
9. Optimization and business reviews
10. Monitoring
11. Renewal, suspension, or termination

Risk tiers: Low, Medium, High, Prohibited. Re-score after ownership changes, material volume spikes, complaints, abnormal traffic, or policy violations.

## Governance

Run a monthly Affiliate Risk and Compliance Committee with Partnerships, Finance, Legal, Privacy, Fraud/Risk, Security, Brand, and an assurance observer. Review high-risk approvals, exceptions, fraud losses, complaints, incidents, reconciliation breaks, payment exceptions, contract deviations, and material tracking/payout changes.

Require documented approval for new regulated verticals, countries, high-risk traffic sources, sub-affiliate arrangements, advances or guarantees, commission changes outside approved bands, manual adjustments, policy exceptions, partner reinstatement, and material system changes.

Never allow one person to create and approve a partner, modify payout terms, approve manual adjustments, and release payment.

## Minimum policy set

- Governance and decision-rights policy
- Partner due diligence and onboarding standard
- Acceptable traffic and promotion policy
- Marketing claims, disclosure, and brand-safety policy
- Privacy, consent, cookie, and data-use policy
- Fraud detection, investigation, reversal, and clawback policy
- Commission calculation and payout policy
- Third-party/sub-affiliate standard
- Complaints, takedown, and regulatory response procedure
- Records retention and legal-hold policy
- Security/access-control standard
- Incident management and business-continuity procedures
- Exception and risk-acceptance policy

## Technology baseline

Use first-party click IDs and server-to-server postbacks where possible. Store immutable raw events in object storage; normalize them into a warehouse; maintain a versioned conversion/commission subledger; reconcile tracking, advertiser/network source, ERP, payout provider, and bank.

Every conversion should retain: click ID, advertiser conversion ID, affiliate, placement, offer and terms version, timestamps, value/currency, attribution rule, status history, reversal reason, commission, and payment status.

Use idempotency keys and deduplicate on advertiser plus order/conversion ID. No hard deletes.

## Finance controls

- Version-controlled commission schedules.
- Pending, approved, payable, paid, rejected, reversed, and adjusted statuses.
- Daily/weekly operational reconciliation and monthly finance close.
- Dual approval for payouts and manual adjustments.
- Segregation of partner creation, commission setup, conversion validation, payout release, and ledger posting.
- Reserves for refunds, chargebacks, fraud, taxes, and disputes.
- Payment-detail change verification and sanctions screening.

## KPI hierarchy

North star: validated incremental contribution profit through active affiliate partners.

Growth: net revenue, approved conversions, active advertisers, active affiliates, activation rate, advertiser retention.

Profitability: contribution margin, commission-to-revenue ratio, fraud/reversal loss, fees, payback, outstanding liability.

Quality: approval rate, reversal rate, duplicate rate, tracking match rate, postback latency, unmatched rate, complaints.

Partner health: EPC, payout timeliness, advertiser ROAS/CAC, partner churn, concentration.

## Operating cadence

Daily: tracking, conversion, payout, fraud, broken-link, and high-value partner monitoring.

Weekly: Monday performance, Tuesday pipeline, Wednesday optimization, Thursday product/operations, Friday leadership decisions.

Monthly: financial close, partner-tier review, fraud/compliance review, advertiser business reviews, capacity planning, cohort retention.

Quarterly: strategy, risk appetite, concentration, OKRs, scale/focus/pivot decision, board reporting.

## First 90 days

Days 0–30: appoint executive sponsor and program owner; choose wedge; approve charter, RACI, risk policy, commission rules, contracts, tracking design, finance reconciliation, and pilot partners.

Days 31–60: configure tracking, warehouse/reporting, payments, tax, due diligence, fraud rules, creative library, partner onboarding, and controlled beta.

Days 61–90: validate economics, tracking, payouts, quality, and compliance; fix defects; launch governance cadence; expand only after gate approval.

## Affiliate-manager handoff package

The manager must receive:

1. Program charter and objectives
2. Governance key/decision-rights matrix (never passwords or secret credentials)
3. RACI and escalation map
4. Partner lifecycle SOP
5. Partner application and due-diligence checklist
6. Risk-tier rubric
7. Standard affiliate agreement and policy links
8. Offer setup and commission specification
9. Tracking/postback integration guide
10. Finance reconciliation and payout SOP
11. Fraud monitoring and investigation playbook
12. Creative/claims approval checklist
13. KPI dashboard definitions
14. Weekly/monthly/quarterly meeting templates
15. Decision, incident, exception, and partner registries
16. 30/60/90-day onboarding plan
17. Access matrix showing least-privilege permissions
18. Known assumptions, open decisions, and dependency owners

## Handoff rules

- Do not share API keys, passwords, recovery codes, private tokens, or governance credentials in documents or chat. Transfer access through the approved password manager/identity system and record the grant in the access matrix.
- Share only the minimum vaults/pages needed for the role, preferably read-only by default.
- Confirm the manager's exact identity and approved email/account before granting access.
- Obtain governance approval for access to sensitive customer, payout, tax, legal, or fraud-investigation data.
- Schedule a handoff review and require the manager to complete a shadow-to-own transition: observe, execute with review, then own.
- After acceptance, route routine program questions to the manager; retain executive escalation for material risk, policy exceptions, and board-level decisions.

## Definition of done

A new program is launched only when every active partner has identity verification, risk tier, contract, approved traffic sources, and payment details; every commission is traceable from event to payout; high-risk exceptions have owners and expiry dates; incidents have SLAs; monthly reconciliation works; dashboards are live; and the affiliate manager has passed the handoff checklist.