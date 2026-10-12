/**
 * Typed client for the SwapDesk agent backend (docs/API_CONTRACT.md).
 *
 * Only the base URL is configurable, via NEXT_PUBLIC_SWAPDESK_API
 * (default https://swapdesk-7yvl.onrender.com). No secrets ever live in
 * browser code: this backend has no auth. Every call is single-shot —
 * no retries here.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_SWAPDESK_API?.replace(/\/$/, "") ??
  "https://swapdesk-7yvl.onrender.com";

export type HealthOut = {
  ok: boolean;
  service: string;
};

export type ReadyOut = {
  ok: boolean;
  service: string;
  queued_depth: number;
  oldest_queued_age_s: number | null;
  last_terminal_at: string | null;
  note: string;
};

export type ExecutionStatus =
  | "queued"
  | "running"
  | "waiting_input"
  | "completed"
  | "failed";

export type Outcome =
  | "arranged"
  | "clarification"
  | "denial"
  | "escalation"
  | null;

export type AgentCase = {
  case_id: string;
  message: string;
  order_id: string | null;
  order_item_id: string | null;
  size: string | null;
  qty: number;
  execution_status: ExecutionStatus;
  outcome: Outcome;
  current_run_id: string;
  runs: string[];
  created_at: string;
  updated_at: string;
  reply: string | null;
  clarification?: string | null;
};

export type CaseList = {
  items: AgentCase[];
  next_cursor: string | null;
  total: number;
  summary: {
    execution_status: Record<string, number>;
    outcome: Record<string, number>;
    completion?: { arranged: number; total: number; rate: string | null } | null;
  };
};

export type CaseDetail = AgentCase & {
  clarification: string | null;
  cleanup: string | null;
  trace_id: string | null;
  error: string | null;
  requests_spent: number | null;
  exchange_id: string | null;
};

export type TimelineEvent = {
  op_key: string;
  run_id: string;
  op_type: string;
  event: string;
  status: string;
  result: Record<string, unknown>;
  created_at: string;
};

export type AcceptResponse = {
  case_id: string;
  run_id: string;
  execution_status: ExecutionStatus;
  status_url: string;
  duplicate: boolean;
};

export type InventoryItem = {
  sku: string;
  size: string;
  on_hand: number;
  held: number;
  available: number;
};

export type InventoryList = {
  items: InventoryItem[];
  limit: number;
  offset: number;
  total: number;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    console.error(`SwapDesk API unreachable at ${API_BASE}. Is the backend running?`);
    throw new ApiError(0, "Service unreachable.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) detail = body.detail;
    } catch {
      /* keep status text */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthOut> {
  return request<HealthOut>("/v1/health");
}

export function getReady(): Promise<ReadyOut> {
  return request<ReadyOut>("/v1/ready");
}

export function submitTicket(body: {
  message: string;
  order_id?: string | null;
  order_item_id?: string | null;
  size?: string | null;
  qty?: number;
  consent_size?: string | null;
  case_id?: string | null;
  idempotency_key?: string | null;
}): Promise<AcceptResponse> {
  return request<AcceptResponse>("/v1/agent/tickets", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listCases(params?: {
  execution?: string;
  outcome?: string;
  limit?: number;
  cursor?: string | null;
}): Promise<CaseList> {
  const q = new URLSearchParams();
  if (params?.execution) q.set("execution", params.execution);
  if (params?.outcome) q.set("outcome", params.outcome);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.cursor) q.set("cursor", params.cursor);
  const suffix = q.size > 0 ? `?${q.toString()}` : "";
  return request<CaseList>(`/v1/agent/cases${suffix}`);
}

export function getCase(caseId: string): Promise<CaseDetail> {
  return request<CaseDetail>(`/v1/agent/cases/${encodeURIComponent(caseId)}`);
}

export function getTimeline(caseId: string): Promise<TimelineEvent[]> {
  return request<TimelineEvent[]>(
    `/v1/agent/cases/${encodeURIComponent(caseId)}/timeline`,
  );
}

export type ContinueQueued = {
  case_id: string;
  run_id: string;
  execution_status: ExecutionStatus;
  continued: true;
  outcome: null;
  reply: null;
  exchange_id: null;
};

export type ContinueTerminal = {
  case_id: string;
  run_id: string | null;
  execution_status: ExecutionStatus;
  continued: false;
  outcome: Exclude<Outcome, null>;
  reply: string | null;
  exchange_id: string | null;
};

export function continueCase(
  caseId: string,
  body: {
    message?: string | null;
    consent_size?: string | null;
    order_id?: string | null;
    order_item_id?: string | null;
    size?: string | null;
    qty?: number;
  },
): Promise<ContinueQueued | ContinueTerminal> {
  return request<ContinueQueued | ContinueTerminal>(
    `/v1/agent/cases/${encodeURIComponent(caseId)}/continue`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function getInventory(params?: {
  sku?: string;
  size?: string;
  limit?: number;
  offset?: number;
}): Promise<InventoryList> {
  const q = new URLSearchParams();
  if (params?.sku) q.set("sku", params.sku);
  if (params?.size) q.set("size", params.size);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const suffix = q.size > 0 ? `?${q.toString()}` : "";
  return request<InventoryList>(`/v1/inventory${suffix}`);
}

export function isTerminalExecution(status: ExecutionStatus): boolean {
  return status === "completed" || status === "failed";
}
