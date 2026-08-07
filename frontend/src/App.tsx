import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchInbound, triageMessage } from "./api/client";
import { FilterBar } from "./components/FilterBar";
import { MessageList } from "./components/MessageList";
import { runWithLimit } from "./lib/limiter";
import { selectVisible } from "./lib/selectors";
import type { CategoryFilter, InboundMessage, PriorityFilter, RowState } from "./types";

/** Enough to keep the list moving, few enough to stay inside any sane rate limit. */
const MAX_CONCURRENT_TRIAGE_CALLS = 3;

export default function App() {
  const [messages, setMessages] = useState<InboundMessage[]>([]);
  const [rowStates, setRowStates] = useState<Record<string, RowState>>({});
  const [listStatus, setListStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("all");
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all");

  // StrictMode intentionally mounts -> cleans up -> mounts again in dev. This
  // guard (rather than the usual `cancelled` cleanup flag, which would discard
  // the real fetch's result when the first mount's cleanup fires) makes the
  // list load and the auto-triage fan-out happen exactly once, so a dev reload
  // never double-spends on billed calls.
  const hasLoadedRef = useRef(false);

  const triageOne = useCallback((id: string, options?: { refresh?: boolean }) => {
    setRowStates((prev) => ({ ...prev, [id]: { status: "loading" } }));
    return triageMessage(id, options)
      .then((response) => {
        setRowStates((prev) => ({ ...prev, [id]: { status: "done", response } }));
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        setRowStates((prev) => ({ ...prev, [id]: { status: "error", message } }));
      });
  }, []);

  useEffect(() => {
    if (hasLoadedRef.current) return;
    hasLoadedRef.current = true;

    fetchInbound()
      .then((items) => {
        setMessages(items);
        setListStatus("ready");
        setRowStates(Object.fromEntries(items.map((m) => [m.id, { status: "idle" } as RowState])));
        void runWithLimit(
          items.map((m) => () => triageOne(m.id)),
          MAX_CONCURRENT_TRIAGE_CALLS,
        );
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : String(err));
        setListStatus("failed");
      });
  }, [triageOne]);

  const selection = useMemo(
    () =>
      selectVisible(messages, rowStates, { category: categoryFilter, priority: priorityFilter }),
    [messages, rowStates, categoryFilter, priorityFilter],
  );

  return (
    <div className="app">
      <header className="app-header">
        <p className="firm">Northwind Advisors</p>
        <h1>Inbound triage</h1>
        <p className="subtitle">
          The shared inbox, read one message at a time: a summary, a category, a priority and the
          next step for whoever picks it up.
        </p>
      </header>

      <main>
        {loadError && (
          <p className="load-error" role="alert">
            Failed to load inbound messages: {loadError}
          </p>
        )}

        <FilterBar
          category={categoryFilter}
          priority={priorityFilter}
          onCategoryChange={setCategoryFilter}
          onPriorityChange={setPriorityFilter}
          total={messages.length}
          visible={selection.visible.length}
          unresolved={selection.unresolved}
        />

        <h2 className="visually-hidden">Messages</h2>
        <MessageList
          status={listStatus}
          total={messages.length}
          messages={selection.visible}
          rowStates={rowStates}
          onRetry={(id) => triageOne(id, { refresh: true })}
        />
      </main>
    </div>
  );
}
