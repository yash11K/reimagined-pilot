import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1",
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    // Light logging; component layer surfaces to user
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("[api]", err?.response?.status, err?.config?.url, err?.message);
    }
    return Promise.reject(err);
  }
);

export const sseUrl = (path: string) =>
  `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"}${path}`;
