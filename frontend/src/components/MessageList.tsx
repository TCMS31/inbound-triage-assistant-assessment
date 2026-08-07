import type { InboundMessage, RowState } from "../types";
import { MessageCard } from "./MessageCard";

interface Props {
  messages: InboundMessage[];
  rowStates: Record<string, RowState>;
  onRetry: (id: string) => void;
}

export function MessageList({ messages, rowStates, onRetry }: Props) {
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
