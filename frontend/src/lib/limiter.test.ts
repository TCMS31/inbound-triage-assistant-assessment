import { describe, expect, it } from "vitest";
import { runWithLimit } from "./limiter";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("runWithLimit", () => {
  it("runs every task", async () => {
    const seen: number[] = [];
    await runWithLimit(
      [1, 2, 3, 4, 5].map((n) => () => {
        seen.push(n);
        return Promise.resolve(n);
      }),
      2,
    );
    expect(seen.sort()).toEqual([1, 2, 3, 4, 5]);
  });

  it("never exceeds the concurrency cap", async () => {
    // The cap is what keeps a page load from firing one billed call per row
    // simultaneously at a rate-limited API.
    let inFlight = 0;
    let peak = 0;
    const gates = Array.from({ length: 9 }, () => deferred<void>());

    const run = runWithLimit(
      gates.map((gate) => async () => {
        inFlight += 1;
        peak = Math.max(peak, inFlight);
        await gate.promise;
        inFlight -= 1;
      }),
      3,
    );

    for (const gate of gates) {
      gate.resolve();
      await Promise.resolve();
    }
    await run;
    expect(peak).toBe(3);
  });

  it("keeps going after a task rejects", async () => {
    const settled: Array<[number, unknown]> = [];
    await runWithLimit(
      [
        () => Promise.resolve("ok"),
        () => Promise.reject(new Error("boom")),
        () => Promise.resolve("also ok"),
      ],
      2,
      (index, _result, error) => settled.push([index, error]),
    );
    expect(settled).toHaveLength(3);
    expect(settled.find(([index]) => index === 1)?.[1]).toBeInstanceOf(Error);
  });

  it("reports results positionally", async () => {
    const results: Array<string | undefined> = [];
    await runWithLimit(
      ["a", "b", "c"].map((value) => () => Promise.resolve(value)),
      1,
      (index, result) => {
        results[index] = result;
      },
    );
    expect(results).toEqual(["a", "b", "c"]);
  });

  it("handles an empty task list without hanging", async () => {
    await expect(runWithLimit([], 4)).resolves.toBeUndefined();
  });

  it("handles a cap larger than the task count", async () => {
    const seen: number[] = [];
    await runWithLimit([() => Promise.resolve(seen.push(1))], 10);
    expect(seen).toEqual([1]);
  });
});
