/**
 * Extracts the X-Request-Id from an API error (attached by the axios interceptor).
 * Returns a short suffix like "ref: a3f9b1" for display in error toasts,
 * or undefined if no request ID is available.
 */
export function getErrorRef(err: unknown): string | undefined {
  if (typeof err !== "object" || err === null) return undefined;
  const id = (err as { requestId?: string }).requestId;
  if (!id) return undefined;
  // Show first 6 chars for brevity
  return `ref: ${id.slice(0, 8)}`;
}

/**
 * Builds an error message string with optional request ID suffix.
 * Example: "Network error · ref: a3f9b1c2"
 */
export function errorWithRef(err: unknown, fallback = "Something went wrong"): string {
  const msg = err instanceof Error ? err.message : fallback;
  const ref = getErrorRef(err);
  return ref ? `${msg} · ${ref}` : msg;
}
