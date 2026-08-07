// Filtering logic, deliberately outside the components: it is the one piece of
// real behaviour on this side of the wire, and it is worth testing without a
// DOM.
import type {
  CategoryFilter,
  InboundMessage,
  PriorityFilter,
  RowState,
  TriageResult,
} from "../types";

export function resultOf(state: RowState | undefined): TriageResult | null {
  if (state?.status !== "done") return null;
  return state.response.error ? null : state.response.result;
}

/**
 * A row is unresolved while it is queued, in flight, or has failed. It has no
 * category or priority yet, so no filter can honestly include or exclude it.
 */
export function isUnresolved(state: RowState | undefined): boolean {
  if (state === undefined) return true;
  if (state.status === "idle" || state.status === "loading" || state.status === "error") {
    return true;
  }
  return state.response.error || state.response.result === null;
}

export interface Filters {
  category: CategoryFilter;
  priority: PriorityFilter;
}

export interface Selection {
  visible: InboundMessage[];
  /** Unresolved rows kept visible despite an active filter. */
  unresolved: number;
  filtersActive: boolean;
}

/**
 * Apply the filters, but never hide a row that has not been triaged yet.
 *
 * Dropping unresolved rows was the original behaviour, and it is the wrong
 * default for a triage tool: filtering to `high` would silently hide the one
 * message whose classification failed, which is exactly the message a human
 * needs to see.
 */
export function selectVisible(
  messages: InboundMessage[],
  rowStates: Record<string, RowState>,
  filters: Filters,
): Selection {
  const filtersActive = filters.category !== "all" || filters.priority !== "all";
  if (!filtersActive) {
    return { visible: messages, unresolved: 0, filtersActive };
  }

  let unresolved = 0;
  const visible = messages.filter((message) => {
    const state = rowStates[message.id];
    if (isUnresolved(state)) {
      unresolved += 1;
      return true;
    }
    const result = resultOf(state);
    if (result === null) return false;
    if (filters.category !== "all" && result.category !== filters.category) return false;
    if (filters.priority !== "all" && result.priority !== filters.priority) return false;
    return true;
  });

  return { visible, unresolved, filtersActive };
}
