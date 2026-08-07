import type { InboundMessage, TriageResponse } from "../types";

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export function fetchInbound(): Promise<InboundMessage[]> {
  return fetch("/api/inbound").then((res) => asJson<InboundMessage[]>(res));
}

/**
 * Triage one message. `refresh` bypasses the server-side cache, which is what
 * the Retry button needs: without it a cached row can never be re-triaged.
 */
export function triageMessage(
  id: string,
  options: { refresh?: boolean } = {},
): Promise<TriageResponse> {
  const query = options.refresh ? "?refresh=true" : "";
  return fetch(`/api/triage/${encodeURIComponent(id)}${query}`, { method: "POST" }).then((res) =>
    asJson<TriageResponse>(res),
  );
}
