import type { InboundMessage, RowState } from "../types";
import { MessageCard } from "./MessageCard";

interface Props {
  status: "loading" | "ready" | "failed";
  /** Size of the inbox before filtering, to tell "empty" from "filtered out". */
  total: number;
  messages: InboundMessage[];
  rowStates: Record<string, RowState>;
  onRetry: (id: string) => void;
}

export function MessageList({ status, total, messages, rowStates, onRetry }: Props) {
  if (status === "loading") {
    return (
      <p className="empty-state" role="status">
        Loading inbound messages…
      </p>
    );
  }
  // The load error is already announced above the filters.
  if (status === "failed") return null;
  if (total === 0) {
    return <p className="empty-state">The inbox is empty — nothing to triage.</p>;
  }
  if (messages.length === 0) {
    return <p className="empty-state">No messages match the current filters.</p>;
  }

  return (
    <div className="message-list">
      {messages.map((message) => (
        <MessageCard
          key={message.id}
          message={message}
          state={rowStates[message.id] ?? { status: "idle" }}
          onRetry={onRetry}
        />
      ))}
    </div>
  );
}
