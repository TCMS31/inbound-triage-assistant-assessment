import type { TriageResponse, TriageSource } from "../types";

const CACHED_PREFIX = "cached:";
const ORIGINS: ReadonlySet<string> = new Set<TriageSource>([
  "llm",
  "baseline",
  "heuristic",
  "fallback",
]);
/** Bookkeeping flags the backend adds; everything else is a reason a message was flagged. */
const METADATA_PREFIXES = [CACHED_PREFIX, "provider:", "attempts:"];

export interface Provenance {
  /** What actually produced the result, looking through a cache hit. */
  origin: Exclude<TriageSource, "cache">;
  cached: boolean;
  /** First heuristic reason, for rows the malformed pre-check resolved. */
  heuristicReason: string | null;
}

/**
 * A cache hit comes back as `source: "cache"` with a `cached:<origin>` flag.
 * Reading only `source` would drop the baseline and heuristic badges on every
 * reload, so an offline rule result would look like a cached model result.
 */
export function provenanceOf(response: TriageResponse): Provenance {
  let origin: Provenance["origin"] = "llm";
  let cached = false;

  if (response.source === "cache") {
    cached = true;
    const marker = response.flags.find((flag) => flag.startsWith(CACHED_PREFIX));
    const recorded = marker?.slice(CACHED_PREFIX.length);
    if (recorded && ORIGINS.has(recorded)) origin = recorded as Provenance["origin"];
  } else {
    origin = response.source;
  }

  const reasons = response.flags.filter(
    (flag) => !METADATA_PREFIXES.some((prefix) => flag.startsWith(prefix)),
  );
  return {
    origin,
    cached,
    heuristicReason: origin === "heuristic" ? (reasons[0] ?? null) : null,
  };
}
