import axios from "axios";
import { uuid } from "@/lib/uuid";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1",
  headers: { "Content-Type": "application/json" },
});

// Attach a client-generated X-Request-Id on every request so the backend
// echoes it back — useful for correlating errors in logs and support tickets.
apiClient.interceptors.request.use((config) => {
  config.headers["X-Request-Id"] = uuid();
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    // Attach the server's X-Request-Id to the error for downstream consumers
    // (e.g. error toasts can display "ref: <id>" for support tickets).
    const requestId =
      err?.response?.headers?.["x-request-id"] ??
      err?.config?.headers?.["X-Request-Id"];
    if (requestId) {
      err.requestId = requestId;
    }

    if (import.meta.env.DEV) {
      console.warn("[api]", err?.response?.status, err?.config?.url, err?.message, requestId ? `ref:${requestId}` : "");
    }
    return Promise.reject(err);
  }
);

export const sseUrl = (path: string) =>
  `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"}${path}`;
