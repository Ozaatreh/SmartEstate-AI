import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";

export type ExecutionStatus = "pending" | "running" | "succeeded" | "failed" | "skipped" | "cancelled";

export interface WorkflowStats {
  window_hours: number;
  succeeded: number;
  failed: number;
  skipped: number;
  running: number;
  pending: number;
  cancelled: number;
  last_execution_id: string | null;
  last_status: ExecutionStatus | null;
  last_finished_at: string | null;
  avg_duration_ms: number | null;
}

export interface Workflow {
  key: string;
  name: string;
  description: string;
  category: string;
  version: number;
  is_enabled: boolean;
  is_registered: boolean;
  event_types: string[];
  schedule_minutes: number | null;
  timeout_seconds: number;
  max_attempts: number;
  next_run_at: string | null;
  last_run_at: string | null;
  stats: WorkflowStats;
}

export interface StepDef {
  key: string;
  label: string;
  action: string;
  action_label: string;
  action_description: string;
  advisory: boolean;
  condition: string | null;
  on_error: "fail" | "continue";
}

export interface Parameter {
  name: string;
  type: "int" | "number" | "bool";
  label: string;
  description: string;
  value: number | boolean;
  default: number | boolean;
  minimum: number | null;
  maximum: number | null;
  unit: string | null;
}

export interface WorkflowDetail extends Workflow {
  conditions: string[];
  steps: StepDef[];
  parameters: Parameter[];
  can_manage: boolean;
  can_operate: boolean;
}

export interface Execution {
  id: string;
  workflow_key: string;
  workflow_name: string;
  workflow_version: number;
  trigger_type: "event" | "schedule" | "manual";
  event_type: string | null;
  entity_type: string | null;
  entity_id: string | null;
  entity_label: string | null;
  status: ExecutionStatus;
  attempt: number;
  max_attempts: number;
  available_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  lease_owner: string | null;
  lease_expires_at: string | null;
  created_at: string;
}

export interface StepRun {
  id: string;
  step_key: string;
  step_index: number;
  action_key: string;
  attempt: number;
  status: "succeeded" | "failed" | "skipped";
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string;
  duration_ms: number;
}

export interface LogEntry {
  seq: number;
  attempt: number;
  level: "debug" | "info" | "warning" | "error";
  step_key: string | null;
  message: string;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface ExecutionDetail extends Execution {
  context: Record<string, unknown>;
  result: Record<string, unknown> | null;
  triggered_by: string | null;
  steps: StepRun[];
  planned_steps: StepDef[];
  logs: LogEntry[];
  allowed_actions: ("retry" | "cancel")[];
}

export interface Overview {
  window_hours: number;
  executions: number;
  succeeded: number;
  failed: number;
  skipped: number;
  in_progress: number;
  success_rate: number | null;
  queued_events: number;
  queued_executions: number;
  retry_scheduled: number;
  workers: { worker_id: string; hostname: string; pid: number; started_at: string; last_seen_at: string; executions_completed: number; online: boolean }[];
  workers_online: number;
}

const key = ["automation"] as const;
/** Live views poll while something is queued or running. */
const LIVE_MS = 5_000;

export function useOverview() {
  return useQuery({ queryKey: [...key, "overview"], queryFn: () => api.get<Overview>("/automation/overview"), refetchInterval: LIVE_MS });
}

export function useWorkflows() {
  return useQuery({ queryKey: [...key, "workflows"], queryFn: () => api.get<Workflow[]>("/automation/workflows"), refetchInterval: 15_000 });
}

export function useWorkflow(workflowKey: string | undefined) {
  return useQuery({ queryKey: [...key, "workflow", workflowKey], queryFn: () => api.get<WorkflowDetail>(`/automation/workflows/${workflowKey}`), enabled: Boolean(workflowKey) });
}

export function useExecutions(query: ListQuery & { workflow_key?: string; status?: string; trigger_type?: string; entity_id?: string }) {
  return useQuery({
    queryKey: [...key, "executions", query],
    queryFn: ({ signal }) => api.get<Page<Execution>>("/automation/executions", { ...query }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((e) => e.status === "pending" || e.status === "running") ? LIVE_MS : false),
  });
}

export function useExecution(id: string | undefined) {
  return useQuery({
    queryKey: [...key, "execution", id],
    queryFn: () => api.get<ExecutionDetail>(`/automation/executions/${id}`),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && ["pending", "running"].includes(q.state.data.status) ? 2_000 : false),
  });
}

export function useUpdateWorkflow(workflowKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { is_enabled?: boolean; parameters?: Record<string, number | boolean>; timeout_seconds?: number; max_attempts?: number }) =>
      api.patch<WorkflowDetail>(`/automation/workflows/${workflowKey}`, body),
    onSuccess: (data) => {
      qc.setQueryData([...key, "workflow", workflowKey], data);
      void qc.invalidateQueries({ queryKey: key });
    },
  });
}

export function useRunWorkflow(workflowKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ execution_id: string }>(`/automation/workflows/${workflowKey}/run`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useExecutionAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "retry" | "cancel") => api.post<ExecutionDetail>(`/automation/executions/${id}/${action}`),
    onSuccess: (data) => {
      qc.setQueryData([...key, "execution", id], data);
      void qc.invalidateQueries({ queryKey: key });
    },
  });
}
