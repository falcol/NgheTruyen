/**
 * Concurrency limiter shared by TTS engines (module-level state → one limit
 * per server isolate / dev process). Waiters bail out with AbortError if the
 * client disconnects while queued — otherwise zombie requests would hold
 * slots for tens of seconds.
 */
export function createLimiter(maxConcurrent: number) {
  let active = 0;
  const waitQueue: Array<() => void> = [];

  return async function withSlot<T>(
    fn: () => Promise<T>,
    signal?: AbortSignal,
  ): Promise<T> {
    if (signal?.aborted) {
      throw new DOMException("Request aborted.", "AbortError");
    }
    if (active >= maxConcurrent) {
      await new Promise<void>((resolve, reject) => {
        const onAbort = () => reject(new DOMException("Request aborted.", "AbortError"));
        if (signal) {
          if (signal.aborted) return onAbort();
          signal.addEventListener("abort", onAbort, { once: true });
        }
        waitQueue.push(() => {
          signal?.removeEventListener("abort", onAbort);
          resolve();
        });
      });
    }
    if (signal?.aborted) {
      // Client is gone — pass the freed/unused slot to the next waiter.
      const next = waitQueue.shift();
      if (next) next();
      throw new DOMException("Request aborted.", "AbortError");
    }
    active += 1;
    try {
      return await fn();
    } finally {
      active -= 1;
      const next = waitQueue.shift();
      if (next) next();
    }
  };
}
