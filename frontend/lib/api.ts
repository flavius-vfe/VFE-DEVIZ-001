export function apiBase(): string {
  if (typeof window === "undefined") return "";
  const port = 8030;
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
}

export async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`${apiBase()}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Eroare HTTP ${response.status}`);
  }
  return payload;
}
