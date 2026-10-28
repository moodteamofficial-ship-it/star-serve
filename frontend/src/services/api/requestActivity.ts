/** In-flight mutating API activity — drives the global top loader (writes only). */

type Listener = () => void;

let pending = 0;
let holds = 0;
const listeners = new Set<Listener>();

function notify() {
  for (const listener of listeners) listener();
}

export function beginRequest(): void {
  pending += 1;
  notify();
}

export function endRequest(): void {
  pending = Math.max(0, pending - 1);
  notify();
}

/** Keep the top loader visible (e.g. sign-in min duration) even with no pending request. */
export function holdTopLoader(): () => void {
  holds += 1;
  notify();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    holds = Math.max(0, holds - 1);
    notify();
  };
}

export function isRequestActive(): boolean {
  return pending > 0 || holds > 0;
}

export function subscribeRequestActivity(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
