# Business workflows

Four separate workflows, each implemented in the API (diagrams in Mermaid — they render on GitHub and in most
Markdown viewers). Automated steps run as registered workflows in the automation engine (`app/automation`).

## 1. Customer and sales

```mermaid
flowchart LR
  A[Website inquiry / viewing request<br/>or staff registers lead] --> B[CRM lead created<br/>event: lead.created]
  B --> C[Lead scoring<br/>transparent rules]
  C --> D[Round-robin assignment<br/>to an active sales agent]
  D --> E[Follow-up activities<br/>SLA timer]
  E -->|overdue| E2[Escalation notice<br/>crm.follow_up_sla]
  E --> F{Unit chosen?}
  F -->|yes| G[Reservation<br/>unit locked, expiry date]
  G -->|expires| H[Released automatically<br/>crm.reservation_expiry]
  G -->|converted| I[Won · unit sold]
  F -->|no| J[Lost / nurture]
```

Stages: new → contacted → qualified → viewing → negotiation → won / lost. Only one active reservation per unit
(database constraint); a reservation locks the unit until it expires or is converted.

## 2. Procurement

```mermaid
flowchart LR
  A[Purchase request<br/>draft] --> B[Submit]
  B --> C{Budget available?<br/>finance.budget_validation}
  C -->|no| X[Blocked with reason]
  C -->|yes| D[Approval routing<br/>department → finance → executive by amount]
  D -->|reject / changes| A
  D --> E[Quotations compared<br/>procurement.supplier_analysis]
  E --> F[Final approval]
  F --> G[Budget committed<br/>append-only ledger]
  G --> H[Purchase order created and issued]
  H -->|cancelled| I[Commitment released]
  H -->|replaced| J[Old PO released, new PO committed<br/>in one transaction]
```

Requesters never approve their own documents; amounts are exact decimals; every step is audited.

## 3. Marketing content

```mermaid
flowchart LR
  A[Draft content<br/>project facts checked] --> B[Submit for review]
  B --> C{Marketing manager}
  C -->|request changes| D[Author revises<br/>new version kept]
  D --> B
  C -->|approve| E[Approved version]
  E --> F[Manual publishing decision<br/>no auto-posting]
```

Authors and editors of an item are excluded from approving it; versions and the review history are kept.
AI drafting exists behind `AI_MARKETING_STUDIO_ENABLED` and is **switched off**.

## 4. Automation engine

```mermaid
flowchart LR
  T[Trigger<br/>business event or schedule] --> C{Conditions<br/>plain Python}
  C -->|not met| S[Skipped, logged]
  C -->|met| Q[Execution queued in PostgreSQL]
  Q --> W[Worker claims<br/>FOR UPDATE SKIP LOCKED + lease]
  W --> A[Registered action runs]
  A -->|success| OK[Succeeded]
  A -->|transient error| R[Retry with backoff<br/>30 s, 60 s, 120 s… ±20 %]
  R --> W
  A -->|permanent error / last attempt| F[Failed — visible, retry by staff]
  OK --> H[(Execution history:<br/>steps, logs, attempts)]
  F --> H
```

Registered workflows: `procurement.purchase_request_approval`, `procurement.supplier_analysis`,
`finance.budget_validation`, `crm.lead_registration`, `crm.follow_up_sla`, `crm.reservation_expiry`,
`marketing.content_review`.
