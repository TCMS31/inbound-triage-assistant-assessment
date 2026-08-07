// Tiny concurrency limiter — runs `tasks` with at most `max` in flight at
// once. Used to auto-triage all rows on load without firing 13 simultaneous
// requests at the LLM.
export function runWithLimit<T>(
  tasks: Array<() => Promise<T>>,
  max: number,
  onSettle?: (index: number, result: T | undefined, error: unknown) => void,
): Promise<void> {
  let next = 0;

  async function worker() {
    while (next < tasks.length) {
      const index = next++;
      try {
        const result = await tasks[index]();
        onSettle?.(index, result, undefined);
      } catch (error) {
        onSettle?.(index, undefined, error);
      }
    }
  }

  const workers = Array.from({ length: Math.min(max, tasks.length) }, () => worker());
  return Promise.all(workers).then(() => undefined);
}
