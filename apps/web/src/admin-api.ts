export interface AdminSession {
  enabled: boolean;
  authenticated: boolean;
  name?: string;
  email?: string;
  expires_at?: string;
  csrf_token?: string;
}

export interface Overview {
  period_hours: number;
  requests: number;
  successful: number;
  server_errors: number;
  average_duration_ms: number;
}

export interface MonitoringTarget {
  name: string;
  instance: string;
  kind: "service" | "probe";
  available: boolean;
}

export interface MonitoringStatus {
  configured: boolean;
  targets: MonitoringTarget[];
}

export interface QueryRecord {
  id: string;
  request_id: string;
  started_at: string;
  completed_at: string;
  query: string | null;
  username: string | null;
  player_id: number | null;
  mode: string | null;
  requested_limit: number | null;
  score_count: number | null;
  status: number;
  error_code: string | null;
  cache: string | null;
  credentials: string | null;
  api_slot: number | null;
  upstream_requests: number;
  duration_ms: number;
  result_available: boolean;
  result?: unknown;
}

export interface LogEntry {
  timestamp: string;
  service: string;
  level: string;
  event: string | null;
  message: string;
  request_id: string | null;
  fields: Record<string, unknown>;
  raw: string;
}

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail || `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const getAdminSession = () =>
  adminFetch<AdminSession>("/api/admin/session");

export const getOverview = () => adminFetch<Overview>("/api/admin/v1/overview");

export const getMonitoring = () =>
  adminFetch<MonitoringStatus>("/api/admin/v1/monitoring");

export const getRequests = () =>
  adminFetch<{ items: QueryRecord[] }>("/api/admin/v1/requests?limit=50");

export const getRequest = (id: string) =>
  adminFetch<QueryRecord>(`/api/admin/v1/requests/${encodeURIComponent(id)}`);

export const searchLogs = (body: {
  start: string;
  end: string;
  services: string[];
  levels: string[];
  request_id?: string;
  text?: string;
  limit: number;
}) =>
  adminFetch<{ items: LogEntry[] }>("/api/admin/v1/logs/search", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const logout = (csrfToken: string) =>
  adminFetch<void>("/api/admin/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
