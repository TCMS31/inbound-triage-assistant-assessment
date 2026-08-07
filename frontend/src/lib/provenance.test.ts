import { describe, expect, it } from "vitest";
import { provenanceOf } from "./provenance";
import type { TriageResponse } from "../types";

function response(overrides: Partial<TriageResponse>): TriageResponse {
  return {
    id: "inb-001",
    result: {
      summary: "A summary.",
      category: "prospect",
      priority: "medium",
      next_action: "Do the thing.",
    },
    source: "llm",
    flags: [],
    error: false,
    error_message: null,
    ...overrides,
  };
}

describe("provenanceOf", () => {
  it("reports a fresh source as-is", () => {
    expect(provenanceOf(response({ source: "baseline", flags: ["provider:stub"] }))).toEqual({
      origin: "baseline",
      cached: false,
      heuristicReason: null,
    });
  });

  it("keeps the baseline origin through a cache hit", () => {
    const hit = response({ source: "cache", flags: ["provider:stub", "cached:baseline"] });
    expect(provenanceOf(hit)).toEqual({ origin: "baseline", cached: true, heuristicReason: null });
  });

  it("keeps the heuristic reason through a cache hit", () => {
    const hit = response({
      source: "cache",
      flags: ["empty_or_near_empty_body", "cached:heuristic"],
    });
    expect(provenanceOf(hit)).toEqual({
      origin: "heuristic",
      cached: true,
      heuristicReason: "empty_or_near_empty_body",
    });
  });

  it("keeps a fallback origin through a cache hit", () => {
    const hit = response({
      source: "cache",
      flags: ["validation_failed_twice", "provider:anthropic", "cached:fallback"],
    });
    expect(provenanceOf(hit).origin).toBe("fallback");
  });

  it("treats a cache hit with no usable marker as a model result", () => {
    expect(provenanceOf(response({ source: "cache", flags: ["cached:bogus"] })).origin).toBe("llm");
    expect(provenanceOf(response({ source: "cache", flags: [] })).origin).toBe("llm");
  });

  it("ignores bookkeeping flags when picking the heuristic reason", () => {
    const fresh = response({ source: "heuristic", flags: ["garbled_encoding", "garbled_sender"] });
    expect(provenanceOf(fresh).heuristicReason).toBe("garbled_encoding");
  });
});
