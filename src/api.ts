export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `Request failed (${response.status})`,
    );
  }
  return response.json();
}

export function navigate(path: string) {
  window.location.hash = path;
}

export const percent = (n: number | null) => (n === null ? '—' : `${(n * 100).toFixed(1)}%`);
export const shortHash = (hash: string) => hash.slice(0, 10);
export const formatDate = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
