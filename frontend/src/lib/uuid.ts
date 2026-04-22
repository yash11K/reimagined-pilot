/** Generates a random UUID, falling back to a polyfill when
 *  crypto.randomUUID is unavailable (e.g. non-HTTPS contexts). */
let _counter = 0;

export function uuid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    // Fallback for insecure contexts (plain HTTP)
    return `${Date.now()}-${++_counter}-${Math.random().toString(36).slice(2, 10)}`;
  }
}
