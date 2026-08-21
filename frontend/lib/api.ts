declare global {
  interface Window {
    __VFE_DEVIZ_CONFIG__?: { API_URL?: string };
  }
}

export function apiBase(): string {
  if (typeof window === "undefined") return "";
  const override = window.__VFE_DEVIZ_CONFIG__?.API_URL?.trim();
  if (override) return override.replace(/\/$/, "");
  return `${window.location.protocol}//${window.location.hostname}:8030`;
}

export async function api(path: string, options: RequestInit = {}) {
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${apiBase()}${path}`, {
    ...options,
    credentials: "include",
    headers: isForm ? (options.headers || {}) : {"Content-Type":"application/json",...(options.headers || {})}
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Eroare HTTP ${response.status}`);
  }
  return payload;
}
