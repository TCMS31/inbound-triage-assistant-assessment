// Mirrors backend/src/triage_backend/schemas.py — the wire contract, kept in
// one place on the frontend side. If these drift, the backend is right.

export interface InboundMessage {
  id: string;
  received_at: string;
  channel: string;
  from_name: string;
  from_org: string;
  subject: string;
  body: string;
}

export type Category =
  "prospect" | "existing_client" | "vendor_partner" | "noise_other" | "needs_review";

export type Priority = "high" | "medium" | "low";

export interface TriageResult {
  summary: string;
  category: Category;
  priority: Priority;
  next_action: string;
}

/**
 * Where a result came from. `baseline` is the offline rule provider, never a
 * model — the UI labels it so the two can never be confused.
 */
export type TriageSource = "cache" | "llm" | "baseline" | "heuristic" | "fallback";

export interface TriageResponse {
  id: string;
  result: TriageResult | null;
  source: TriageSource;
  flags: string[];
  error: boolean;
  error_message: string | null;
}

// Client-side view state for a row — a superset that also tracks the in-flight
// loading state, which the backend contract has no concept of.
export type RowState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; response: TriageResponse }
  | { status: "error"; message: string };

export type CategoryFilter = Category | "all";
export type PriorityFilter = Priority | "all";
