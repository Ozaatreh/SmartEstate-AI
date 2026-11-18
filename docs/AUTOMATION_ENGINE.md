# SmartEstate AI — Python Automation Engine

> Status: **Implemented in Phase 3.** The prototype ships **predefined Python workflows**. A dynamic
> workflow builder and visual editor are out of scope, but the contracts below are designed so
> definitions can later move into the database without rewriting triggers, conditions or actions.

## 0. As implemented (Phase 3) — differences from the Phase 0 design

| Topic | Implementation |
|---|---|
| Process model | **Separate worker process**: `python -m app.automation.worker` (`--once` drains the queue and exits). Any number of workers can run; each sends a heartbeat (`wf_worker_heartbeats`) shown in the UI. The API never executes workflows. |
| Code layout | `app/automation/`: `contracts.py`, `events.py` (EventBus), `registry.py` (Action Registry + workflow registry), `manager.py` (Workflow Manager), `conditions.py` (Condition Evaluator), `engine.py` (Trigger Manager + Workflow Executor + recovery), `errors.py`, `logs.py`, `actions/`, `workflows.py`, `service.py` / `repository.py` / `router.py` (management API). |
| Claiming | `UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED)` sets `status=running`, increments `attempt` and sets a **lease** (`lease_owner`, `lease_expires_at` = timeout + 30 s). |
| Fencing | Each step re-locks its execution row (`FOR NO KEY UPDATE`, so foreign-key inserts of log rows aren't blocked) and checks owner + attempt before and after the action; a worker that lost its lease raises `LeaseLost` and commits nothing. |
| Timeouts | Per-attempt time budget: PostgreSQL `SET LOCAL statement_timeout` for database work plus a deadline check before commit. An overrun rolls the step back and is a transient failure (`timeout`). Blocking calls outside the database must carry their own timeout (e.g. the AI SDK in Phase 6). |
| Recovery | Executions whose lease expired are requeued with backoff (`abandoned`) or failed after the last attempt. |
| Schedules | `wf_definitions.next_run_at` / `last_run_at` (no separate schedule table); slot idempotency key; missed slots collapse into one run. |
| Clock | All queue comparisons use the database clock (`clock_timestamp()`). |
| Logs | `wf_execution_logs` rows written in their own short transactions, so they survive failed steps. |
| Retry from UI | Failed / cancelled executions get one more attempt (`max_attempts = attempt + 1`); completed steps are reused. Permission `automation.executions.operate`, audited. |

**Workflows shipped:** `procurement.purchase_request_approval` (route check on `purchase_request.sent_for_approval`; reminders and reporting-line escalation every 15 min), `finance.budget_validation` (threshold and over-budget alerts on submit / send-for-approval / ledger change), `procurement.supplier_analysis` (advisory scoring on `purchase_request.quotation_added`), `crm.lead_registration` (score → round-robin assign → notify on `lead.created`; implements the roadmap's `crm.new_lead`). Phase 5 adds `crm.follow_up_sla` and `crm.reservation_expiry` (both every 15 min) and the events `lead.assigned`, `lead.stage_changed`, `lead.follow_up_overdue`, `reservation.{created, cancelled, converted, expired}` and `unit.status_changed` (payloads carry ids and codes only — never lead contact details). Events emitted by Phase 2 services: `purchase_request.{submitted, quotation_added, quotation_selected, sent_for_approval, approved, rejected, cancelled}`, `approval.{requested, decided}`, `budget.ledger_changed`, `lead.created`.

## 1. Principles

1. **Deterministic.** Conditions and business decisions are plain Python. AI output can be
   *recorded* by a step, but no condition that leads to an approval, a financial write or a permission
   change may depend on it.
2. **Actions call services.** An action never touches repositories or SQL directly. So the
   engine automatically obeys the same business rules and permission checks as the API.
3. **Durable and observable.** Every event, execution and step is a PostgreSQL row.
4. **At-least-once delivery, exactly-once effect.** Events may be processed more than once, so
   executions and actions are idempotent.
5. **No new infrastructure.** PostgreSQL is the queue. Workers run as separate Python processes (see § 0).

## 2. Components

| Component | Responsibility | Location |
|---|---|---|
| **EventBus** | `emit(session, event_type, entity, payload)` inserts an `automation_events` row in the caller's transaction (transactional outbox). Modules depend only on this. | `automation/events.py` |
| **Workflow Manager** | The registry of workflow classes. At startup it syncs them to `wf_definitions` (key, version, trigger) and loads `is_enabled` + `parameters`. Lists, enables and disables workflows. | `automation/manager.py` |
| **Trigger Manager** | Maps an event type → enabled workflows. Computes due schedules (`wf_schedule_state`). Handles manual triggers from the admin UI. | `automation/triggers.py` |
| **Condition Evaluator** | Evaluates a workflow's conditions against the execution context. Records the result and the reason in the execution. Conditions are pure functions (no I/O except read-only service queries). | `automation/conditions.py` |
| **Action Registry** | `@action("notify_users")`-registered callables with a typed Pydantic input model, an `idempotent` contract and a retry policy. | `automation/actions/` |
| **Workflow Executor** | Creates the execution (with an idempotency key), runs steps in order, persists step results, applies retry and failure rules. | `automation/executor.py` |
| **Worker / Scheduler loop** | An asyncio task started in the FastAPI lifespan. Each tick: claim pending events (`FOR UPDATE SKIP LOCKED`), fire due schedules, pick up executions due for retry. The blocking DB work runs in a thread. | `automation/worker.py` |
| **Execution History** | `wf_executions` + `wf_step_executions`; a read API and admin UI (filter, detail, retry, cancel). | `automation/history.py`, router |
| **Logging** | Structured logs with `execution_id`, `workflow_key`, `step_key`, `attempt`. | `core/logging.py` |
| **Error Handling** | Classifies errors as transient or permanent, applies backoff, marks the execution failed, and notifies admins once the final attempt fails. | `automation/errors.py` |

## 3. Interfaces (illustrative Python)

```python
# automation/contracts.py
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol
from pydantic import BaseModel

@dataclass(frozen=True)
class EventTrigger:
    event_types: tuple[str, ...]            # e.g. ("purchase_request.submitted",)
    kind: Literal["event"] = "event"

@dataclass(frozen=True)
class ScheduleTrigger:
    every_minutes: int                      # simple interval; cron is a later extension
    kind: Literal["schedule"] = "schedule"

@dataclass(frozen=True)
class ManualTrigger:
    kind: Literal["manual"] = "manual"

Trigger = EventTrigger | ScheduleTrigger | ManualTrigger

@dataclass
class ExecutionContext:
    execution_id: str
    workflow_key: str
    trigger: dict[str, Any]                 # the event row or schedule slot
    parameters: dict[str, Any]              # from wf_definitions.parameters
    data: dict[str, Any] = field(default_factory=dict)   # step outputs, by step key
    services: "ServiceProvider"             # system principal + service accessors

class Condition(Protocol):
    name: str
    def __call__(self, ctx: ExecutionContext) -> "ConditionResult": ...

@dataclass(frozen=True)
class ConditionResult:
    passed: bool
    reason: str

@dataclass(frozen=True)
class Step:
    key: str                                # stable, unique within the workflow
    action: str                             # Action Registry key
    build_input: Callable[[ExecutionContext], BaseModel]
    when: Condition | None = None           # step-level condition (skip if false)
    on_error: Literal["fail", "continue"] = "fail"

class Workflow(Protocol):
    key: str                                # "procurement.pr_routing"
    version: int                            # bump when steps change semantics
    name: str
    trigger: Trigger
    conditions: tuple[Condition, ...]       # all must pass, or the execution is "skipped"
    steps: tuple[Step, ...]
    def idempotency_key(self, trigger: dict[str, Any]) -> str: ...
```

```python
# automation/actions/base.py
class ActionResult(BaseModel):
    output: dict[str, Any] = {}

class ActionSpec:
    key: str
    input_model: type[BaseModel]            # validated before the call (extra="forbid")
    retry: "RetryPolicy"                    # max_attempts, base_delay_s, transient error types
    def run(self, ctx: ExecutionContext, data: BaseModel, step_idem_key: str) -> ActionResult: ...

def action(key: str, *, input_model, retry=DEFAULT_RETRY): ...   # registration decorator
```

Example workflow (abridged):

```python
@register_workflow
class PurchaseRequestRouting:
    key, version, name = "procurement.pr_routing", 1, "Route submitted purchase requests"
    trigger = EventTrigger(("purchase_request.submitted",))
    conditions = (entity_status_is("purchase_request", "pending_approval"),)
    steps = (
        Step("budget", "finance.check_budget", lambda c: BudgetCheckIn(pr_id=c.trigger["entity_id"])),
        Step("open_approval", "approvals.open_request",
             lambda c: OpenApprovalIn(entity_type="purchase_request", entity_id=c.trigger["entity_id"],
                                      over_budget=c.data["budget"]["over_budget"])),
        Step("notify", "notifications.notify_approvers",
             lambda c: NotifyIn(approval_request_id=c.data["open_approval"]["approval_request_id"])),
    )
    def idempotency_key(self, t): return f"{self.key}:v{self.version}:event:{t['event_id']}"
```

## 4. Trigger architecture

| Type | Source | How it fires |
|---|---|---|
| **Event** | A service calls `EventBus.emit()` inside its transaction | The worker claims `pending` events in batches (`SKIP LOCKED`), resolves the workflows subscribed to the type, and creates one execution per workflow. The event becomes `processed` once all executions are created. |
| **Schedule** | `ScheduleTrigger(every_minutes=N)` | Each tick, `wf_schedule_state` rows with `next_fire_at <= now()` are locked and advanced, and one execution is created with key `<wf>:v<n>:slot:<iso-slot>`. Missed slots are collapsed into a single run (no backlog storm after downtime). |
| **Manual** | Admin "Run now" / "Retry" | Requires `automation.workflows.run`. The idempotency key includes a request nonce for "Run now". "Retry" re-runs the same execution. |

Events are facts in the past tense (`lead.created`, `approval.decided`, `purchase_order.issued`),
with a small payload (ids and the minimum needed). Workflows reload current state through services
rather than trusting a stale payload.

## 5. Condition evaluation

- Workflow-level conditions decide whether the execution runs at all. If any fails, the execution
  is `skipped` and the reason is stored (for example: "PR no longer pending_approval").
- Step-level `when` conditions skip individual steps (stored as a `skipped` step).
- Conditions are small named functions from a library (`entity_status_is`, `amount_gte(param)`,
  `lead_has_no_owner`, `budget_utilisation_gte(param)`). Thresholds come from
  `wf_definitions.parameters`, so they can be tuned without a deploy.
- Conditions may read through services; they never write.

## 6. Action registration

- Actions live in `automation/actions/<module>.py` and are registered by key, e.g.
  `finance.check_budget`, `approvals.open_request`, `crm.score_lead`, `crm.assign_lead`,
  `crm.escalate_overdue`, `crm.expire_reservations`, `notifications.notify_users`,
  `notifications.notify_approvers`, `ai.summarise_lead` (advisory only), `dashboard.build_digest`.
- Each action: validates its input model, runs **one** service call in **its own transaction**
  under a **system principal** (`system:automation`, which holds only the permissions the engine needs), returns a JSON-safe output.
- Actions that change state accept the `step_idem_key` and must be idempotent. They use a
  natural unique key or a `dedupe_key` (for example `notifications UNIQUE(user_id, dedupe_key)`,
  `budget_ledger_entries UNIQUE(idempotency_key)`, or "already assigned → return the existing owner").
- AI actions (`ai.*`) are marked `advisory=True`. The registry refuses to let any later step's
  condition read an advisory output.

## 7. Execution lifecycle

```
           create (UNIQUE idempotency_key — duplicate → no-op)
                │
             pending ──▶ running ──▶ succeeded
                │           │
                │           ├──▶ skipped        (workflow conditions false)
                │           │
                │           └──▶ failed ──(transient & attempt < max)──▶ pending (next_retry_at = backoff)
                │                    └──(permanent or final attempt)──▶ failed (final) → admin notification
                └──▶ cancelled (admin)
```

1. **Claim:** lock the execution row (`FOR UPDATE SKIP LOCKED`), set `running`, `attempt += 1`.
2. **Evaluate** workflow conditions → `skipped` or continue.
3. **Run steps** in order. Steps that already `succeeded` in an earlier attempt are **not re-run**;
   their stored output is reloaded into `ctx.data`. So a retry resumes where it stopped.
4. Each step writes a `wf_step_executions` row (input, output, timings, error).
5. **Finish:** `succeeded`, or apply the error policy (§ 9).

Each step commits on its own. Effects that must be atomic with each other belong in **one**
action (one service call). For example, "approve PO + write commitment" is one service method.

## 8. Execution history

- List: workflow, trigger, entity link, status, attempts, duration, started time. Filters by workflow, status and date.
- Detail: the timeline of steps with inputs and outputs (secrets and personal fields redacted), condition reasons and errors.
- Actions: **Retry** (failed), **Cancel** (pending), **Run now** (manual/schedule workflows),
  **Enable/Disable** workflow. All require `automation.*` permissions and are audited.
- Dashboard tile: executions in the last 24 h by status; the latest failures.

## 9. Error handling

| Class | Examples | Behaviour |
|---|---|---|
| **Transient** | DB serialisation/deadlock, connection loss, `ExternalServiceUnavailable` (Claude 429/5xx/timeout) | Retry with exponential backoff + jitter (30 s, 2 min, 10 min; `max_attempts = 3` by default, per action) |
| **Permanent** | `BusinessRuleViolation`, `ValidationFailed`, `NotFound`, `PermissionDenied`, input validation error | Fail immediately; no retry |
| **Bug** | Any other exception | Treated as permanent; full stack trace logged with `execution_id`; message stored truncated |

- `on_error="continue"` is allowed only for non-critical steps (for example notifications or AI summaries).
  Their failure is recorded, and the execution still succeeds with a warning.
- A worker crash leaves rows `running` with a stale `locked_at`. A reaper returns them to `pending`
  after a timeout (5 min). Completed steps are not re-run (§ 7.3).
- An event whose workflow resolution fails is retried up to 5 times, then marked `failed` and shown in the UI.

## 10. Idempotency

| Level | Mechanism |
|---|---|
| Event → execution | `wf_executions.idempotency_key UNIQUE` = `<workflow>:v<version>:event:<event_id>` (or `:slot:<time>`); insert with `ON CONFLICT DO NOTHING` |
| Step retry | Completed steps are skipped on retry (by `step_key`) |
| Action effect | `step_idem_key = <execution_id>:<step_key>` passed to the service, which uses unique constraints / dedupe keys |
| Schedules | One slot fires once (`wf_schedule_state` row lock + slot key) |
| Concurrent workers | `FOR UPDATE SKIP LOCKED` on events and executions |

## 11. Predefined workflows (prototype)

| Key | Trigger | Steps (summary) | Priority |
|---|---|---|---|
| `procurement.pr_routing` | `purchase_request.submitted` | budget check → open approval by policy (over-budget adds tiers) → notify approvers | M |
| `approvals.decision_notify` | `approval.decided` | notify requester → if a next step is open, notify its approvers. (The decision itself, including the final purchase-request approval → budget commitment (D-16), is applied **synchronously** in the approval service transaction, not by this workflow.) | M |
| `finance.budget_threshold_alert` | `budget.ledger_changed` | if utilisation ≥ 80% / 100% (param) → notify finance manager (deduped per threshold) | M |
| `crm.new_lead` — **shipped as `crm.lead_registration`** (key kept for execution history, decision C1) | `lead.created` | deterministic score (incl. timeline and budget fit, Phase 5) → round-robin assign (pool = project code, else `default`, decision C3) → set follow-up due (48 h) → notify agent. AI summary is Phase 6 (decision C4) | M |
| `crm.follow_up_sla` (Phase 5) | schedule 15 min | action `crm.escalate_overdue`: open leads past `next_follow_up_at` → notify holders of `crm.leads.manage` + remind the owner (deduped per lead per day via activity / notification dedupe keys) | M |
| `crm.reservation_expiry` (Phase 5) | schedule 15 min | action `crm.expire_reservations`: `FOR UPDATE SKIP LOCKED` on still-active reservations past `expires_at` → expire + release the unit in the same transaction → notify the lead owner; converted/cancelled rows are never touched | S |
| `hr.leave_routing` | `leave_request.submitted` | open approval (department manager) → notify | S |
| `marketing.content_review` (**built in 7B**) | `marketing_content.submitted` + schedule 15 min | the approval is opened **in the submit transaction**; the workflow verifies the route (an eligible marketing approver who isn't an author) and reminds approvers of content waiting too long (`approvals.send_reminders` scoped to `marketing_content`). Never decides, never publishes | S |
| `dashboard.daily_digest` | schedule daily | compute KPIs → AI narrative (advisory) → notify executives | C |

## 12. Migration to a Dynamic Workflow Engine (future)

The prototype already separates *what can be data* from *what must be code*:

| Today (code) | Already data | Future (data) |
|---|---|---|
| Workflow classes (steps, conditions) | `wf_definitions` key/version/trigger, `is_enabled`, `parameters` | Steps and conditions as versioned JSON (`definition JSONB`) validated against registered actions and condition types |
| Named condition functions | Their parameters | A small, safe expression DSL (comparison/boolean operators over typed context fields) — **never `eval`** |
| Registered actions | Action keys and input schemas (Pydantic → JSON Schema) | A visual editor builds steps from the action catalogue's JSON Schemas |

Migration steps:
1. Expose the action and condition catalogues (key, input JSON Schema, description) through an API.
2. Add `definition JSONB` + `source = code|dynamic` to `wf_definitions`. A `DynamicWorkflow`
   adapter implements the same `Workflow` protocol from JSON, so the executor is unchanged.
3. Version definitions immutably (executions pin `workflow_version`). Publish = new version.
4. Add the visual editor on top of the catalogue API. Add approval for publishing workflows.
5. Optional: move the worker to its own process or replace the outbox poller with a broker behind
   the same `TriggerSource` interface.

The rule stays the same: dynamic workflows can only compose **registered** actions, so business
rules, financial validation and permissions remain in deterministic Python services.
