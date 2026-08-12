import { describe, expect, it } from "vitest";
import { isUnresolved, resultOf, selectVisible } from "./selectors";
import type { InboundMessage, RowState, TriageResponse, TriageResult } from "../types";

function message(id: string): InboundMessage {
  return {
    id,
    received_at: "2025-01-06T09:00:00Z",
    channel: "email",
    from_name: "Someone",
    from_org: "(individual)",
    subject: `Subject ${id}`,
    body: "A body.",
  };
}

function result(overrides: Partial<TriageResult> = {}): TriageResult {
  return {
    summary: "A summary.",
    category: "prospect",
    priority: "medium",
    next_action: "Do the thing.",
    ...overrides,
  };
}

function done(id: string, overrides: Partial<TriageResponse> = {}): RowState {
  return {
    status: "done",
    response: {
      id,
      result: result(),
      source: "llm",
      flags: [],
      error: false,
      error_message: null,
      ...overrides,
    },
  };
}

const MESSAGES = [message("a"), message("b"), message("c")];

describe("resultOf", () => {
  it("returns the result of a completed row", () => {
    expect(resultOf(done("a"))?.category).toBe("prospect");
  });

  it("returns null for rows with no usable result", () => {
    expect(resultOf(undefined)).toBeNull();
    expect(resultOf({ status: "loading" })).toBeNull();
    expect(resultOf({ status: "error", message: "boom" })).toBeNull();
    expect(resultOf(done("a", { error: true, result: null }))).toBeNull();
  });
});

describe("isUnresolved", () => {
  it.each<[string, RowState | undefined]>([
    ["missing", undefined],
    ["idle", { status: "idle" }],
    ["loading", { status: "loading" }],
    ["transport error", { status: "error", message: "network" }],
  ])("treats %s rows as unresolved", (_label, state) => {
    expect(isUnresolved(state)).toBe(true);
  });

  it("treats a per-row API error as unresolved", () => {
    expect(isUnresolved(done("a", { error: true, result: null }))).toBe(true);
  });

  it("treats a completed row as resolved", () => {
    expect(isUnresolved(done("a"))).toBe(false);
  });
});

describe("selectVisible", () => {
  it("returns everything when no filter is set", () => {
    const selection = selectVisible(MESSAGES, {}, { category: "all", priority: "all" });
    expect(selection.visible).toHaveLength(3);
    expect(selection.filtersActive).toBe(false);
    expect(selection.unresolved).toBe(0);
  });

  it("filters on category", () => {
    const states: Record<string, RowState> = {
      a: done("a", { result: result({ category: "prospect" }) }),
      b: done("b", { result: result({ category: "noise_other" }) }),
      c: done("c", { result: result({ category: "prospect" }) }),
    };
    const selection = selectVisible(MESSAGES, states, { category: "prospect", priority: "all" });
    expect(selection.visible.map((m) => m.id)).toEqual(["a", "c"]);
  });

  it("filters on priority", () => {
    const states: Record<string, RowState> = {
      a: done("a", { result: result({ priority: "high" }) }),
      b: done("b", { result: result({ priority: "low" }) }),
      c: done("c", { result: result({ priority: "high" }) }),
    };
    const selection = selectVisible(MESSAGES, states, { category: "all", priority: "high" });
    expect(selection.visible.map((m) => m.id)).toEqual(["a", "c"]);
  });

  it("applies both filters together", () => {
    const states: Record<string, RowState> = {
      a: done("a", { result: result({ category: "existing_client", priority: "high" }) }),
      b: done("b", { result: result({ category: "existing_client", priority: "low" }) }),
      c: done("c", { result: result({ category: "prospect", priority: "high" }) }),
    };
    const selection = selectVisible(MESSAGES, states, {
      category: "existing_client",
      priority: "high",
    });
    expect(selection.visible.map((m) => m.id)).toEqual(["a"]);
  });

  it("never hides a row that failed to triage", () => {
    // The original behaviour dropped these, so filtering to "high" hid the one
    // message nobody had managed to classify.
    const states: Record<string, RowState> = {
      a: done("a", { result: result({ priority: "high" }) }),
      b: done("b", { error: true, result: null, error_message: "429" }),
      c: { status: "loading" },
    };
    const selection = selectVisible(MESSAGES, states, { category: "all", priority: "high" });
    expect(selection.visible.map((m) => m.id)).toEqual(["a", "b", "c"]);
    expect(selection.unresolved).toBe(2);
  });

  it("counts unresolved rows only while a filter is active", () => {
    const states: Record<string, RowState> = { a: { status: "loading" } };
    expect(selectVisible(MESSAGES, states, { category: "all", priority: "all" }).unresolved).toBe(
      0,
    );
  });

  it("preserves the server's ordering", () => {
    const states = Object.fromEntries(MESSAGES.map((m) => [m.id, done(m.id)]));
    const selection = selectVisible(MESSAGES, states, { category: "prospect", priority: "all" });
    expect(selection.visible.map((m) => m.id)).toEqual(["a", "b", "c"]);
  });
});
