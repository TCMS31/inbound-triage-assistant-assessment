import { CATEGORY_LABELS, PRIORITY_LABELS } from "../lib/labels";
import { provenanceOf, type Provenance } from "../lib/provenance";
import type { InboundMessage, RowState, TriageResponse } from "../types";

interface Props {
  message: InboundMessage;
  state: RowState;
  onRetry: (id: string) => void;
}

const SENTINEL_ORGS = new Set(["(individual)", "(unknown)", ""]);

/** Origins worth calling out on a row. `llm` is the unremarkable default. */
const ORIGIN_LABELS: Partial<Record<Provenance["origin"], string>> = {
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
  const priority = state.status === "done" ? state.response.result?.priority : undefined;
  return (
    <article className={`message-card${priority ? ` edge-${priority}` : ""}`}>
      <header>
        <div className="message-meta">
          <span className="message-id">{message.id}</span>
          <span className="channel-badge">{message.channel}</span>
          <span className="from">{senderLabel(message)}</span>
          <time className="received-at" dateTime={message.received_at}>
            {formatReceivedAt(message.received_at)}
          </time>
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
      <span>
        <strong>Triage failed:</strong> {message}
      </span>
      <button type="button" onClick={() => onRetry(id)} aria-label={`Retry triage for ${id}`}>
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

  const { origin, cached, heuristicReason } = provenanceOf(response);
  const originLabel = ORIGIN_LABELS[origin];

  return (
    <div className="triage-result">
      <div className="badges">
        <span className={`badge priority-${result.priority}`}>
          {PRIORITY_LABELS[result.priority]}
        </span>
        <span className="badge category-badge">
          {CATEGORY_LABELS[result.category] ?? result.category}
        </span>
        {heuristicReason && (
          <span className="badge source-badge" title={response.flags.join(", ")}>
            flagged: {heuristicReason}
          </span>
        )}
        {originLabel && <span className="badge source-badge">{originLabel}</span>}
        {cached && <span className="badge source-badge">cached</span>}
      </div>
      <p className="summary">{result.summary}</p>
      <p className="next-action">
        <strong>Next:</strong> {result.next_action}
      </p>
    </div>
  );
}
