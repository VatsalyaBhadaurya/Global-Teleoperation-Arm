import { useInsertionEffect, useRef } from "react";

/**
 * Keeps a ref pointing at the latest `value` without mutating it during
 * render (satisfies `react-hooks/refs`). The update happens in an insertion
 * effect, which runs before any other effect in the same commit, so the ref
 * is current by the time event handlers or layout/passive effects run.
 */
export function useLatest<T>(value: T): { readonly current: T } {
  const ref = useRef(value);
  useInsertionEffect(() => {
    ref.current = value;
  });
  return ref;
}
