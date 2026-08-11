import type { InboundMessage, RowState, TriageResponse, TriageSource } from "../types";

interface Props {
  message: InboundMessage;
  state: RowState;
  onRetry: (id: string) => void;
}

const SENTINEL_ORGS = new Set(["(individual)", "(unknown)", ""]);

const CATEGORY_LABELS: Record<string, string> = {
  prospect: "Prospect",
  existing_client: "Existing client",
  vendor_partner: "Vendor / partner",
  noise_other: "Noise / other",
  needs_review: "Needs review",
};

/** Sources worth calling out on a row. `llm` is the unremarkable default. */
const SOURCE_LABELS: Partial<Record<TriageSource, string>> = {
  cache: "cached",
  baseline: "offline rule baseline — not a model",
  fallback: "model output invalid — fallback",
};

function formatReceivedAt(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function senderLabel(message: InboundMessage): string {
  const name = message.from_name || "(no name)";
  return SENTINEL_ORGS.has(message.from_org) ? name : `${name} — ${message.from_org}`;
}

export function MessageCard({ message, state, onRetry }: Props) {
  return (
    <article className="message-card">
      <header>
        <div className="message-meta">
          <span className="channel-badge">{message.channel}</span>
          <span className="from">{senderLabel(message)}</span>
          <span className="received-at">{formatReceivedAt(message.received_at)}</span>
        </div>
        <h3>{message.subject || "(no subject)"}</h3>
      </header>

      <p className="body-preview">{message.body.trim() || "(empty body)"}</p>

      <div className="triage-panel">
        <TriagePanel state={state} id={message.id} onRetry={onRetry} />
      </div>
    </article>
  );
}

function TriagePanel({
  state,
  id,
  onRetry,
}: {
  state: RowState;
  id: string;
  onRetry: (id: string) => void;
}) {
  switch (state.status) {
    case "idle":
      return <span className="triage-status">Queued…</span>;
    case "loading":
      return (
        <span className="triage-status triage-loading" aria-live="polite">
          Triaging…
        </span>
      );
    case "error":
      return <TriageError message={state.message} id={id} onRetry={onRetry} />;
    case "done":
      return <TriageDone response={state.response} id={id} onRetry={onRetry} />;
  }
}

function TriageError({
  message,
  id,
  onRetry,
}: {
  message: string;
  id: string;
  onRetry: (id: string) => void;
}) {
  return (
    <div className="triage-error" role="alert">
      <span>⚠ Triage failed: {message}</span>
      <button type="button" onClick={() => onRetry(id)}>
        Retry
      </button>
    </div>
  );
}

function TriageDone({
  response,
  id,
  onRetry,
}: {
  response: TriageResponse;
  id: string;
  onRetry: (id: string) => void;
}) {
  if (response.error) {
    return (
      <TriageError message={response.error_message ?? "unknown error"} id={id} onRetry={onRetry} />
    );
  }

  const result = response.result;
  if (!result) return <span className="triage-status">No result returned.</span>;

  const sourceLabel = SOURCE_LABELS[response.source];
  const heuristicFlag = response.source === "heuristic" ? response.flags[0] : null;

  return (
    <div className="triage-result">
      <div className="badges">
        <span className={`badge priority-${result.priority}`}>{result.priority}</span>
        <span className="badge category-badge">
          {CATEGORY_LABELS[result.category] ?? result.category}
        </span>
        {heuristicFlag && (
          <span className="badge source-badge" title={response.flags.join(", ")}>
            flagged: {heuristicFlag}
          </span>
        )}
        {sourceLabel && <span className="badge source-badge">{sourceLabel}</span>}
      </div>
      <p className="summary">{result.summary}</p>
      <p className="next-action">
        <strong>Next:</strong> {result.next_action}
      </p>
    </div>
  );
}
