import { API_BASE_URL } from "../config";
import { clearTokens, loadTokens, saveTokens } from "../auth/storage";
import type { ApiErrorBody, TokenResponse } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;

  constructor(status: number, code: string, message: string, retryable = false) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

type RequestOpts = {
  method?: string;
  body?: unknown;
  auth?: boolean;
  formData?: FormData;
  accessToken?: string | null;
};

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const { refresh } = await loadTokens();
    if (!refresh) return null;
    try {
      const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        await clearTokens();
        return null;
      }
      const data = (await res.json()) as TokenResponse;
      await saveTokens(data.access_token, data.refresh_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody = {};
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    /* ignore */
  }
  const message =
    body.error?.message ||
    (typeof body.detail === "string" ? body.detail : null) ||
    `HTTP ${res.status}`;
  return new ApiError(
    res.status,
    body.error?.code || "HTTP_ERROR",
    message,
    Boolean(body.error?.retryable),
  );
}

export async function apiRequest<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (!opts.formData) headers["Content-Type"] = "application/json";

  let token = opts.accessToken;
  if (opts.auth !== false && token === undefined) {
    token = (await loadTokens()).access;
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const init: RequestInit = {
    method: opts.method || (opts.body || opts.formData ? "POST" : "GET"),
    headers,
  };
  if (opts.formData) init.body = opts.formData;
  else if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  let res = await fetch(url, init);
  if (res.status === 401 && opts.auth !== false) {
    const next = await refreshAccessToken();
    if (next) {
      headers.Authorization = `Bearer ${next}`;
      res = await fetch(url, { ...init, headers });
    }
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  login: (email: string, password: string, device_name?: string) =>
    apiRequest<TokenResponse>("/auth/login", {
      auth: false,
      body: { email, password, device_name },
    }),
  logout: (refresh_token: string | null) =>
    apiRequest<void>("/auth/logout", { body: { refresh_token } }),
  me: () => apiRequest<import("./types").MeResponse>("/auth/me"),
  sessions: () => apiRequest<import("./types").SessionOut[]>("/auth/sessions"),
  revokeSession: (id: string) =>
    apiRequest<void>(`/auth/sessions/${id}/revoke`, { method: "POST", body: {} }),
  health: () => apiRequest<import("./types").HealthOut>("/health", { auth: false }),
  scannerStatus: () => apiRequest<import("./types").ScannerStatusOut>("/scanner/status"),
  candidates: () => apiRequest<import("./types").CandidateOut[]>("/scanner/candidates"),
  ask: (question: string) =>
    apiRequest<import("./types").AskResponse>("/knowledge/ask", { body: { question } }),
  documents: () => apiRequest<Array<Record<string, unknown>>>("/knowledge/documents"),
  strategies: () => apiRequest<Array<Record<string, unknown>>>("/strategies"),
  paperAccount: () => apiRequest<import("./types").PaperAccountOut>("/paper/account"),
  paperTrades: () => apiRequest<import("./types").PaperTradeOut[]>("/paper/trades"),
  acceptPaper: (decision_record_id: string) =>
    apiRequest<import("./types").PaperTradeOut>("/paper/trades", {
      body: { decision_record_id },
    }),
  journal: () => apiRequest<import("./types").JournalEntryOut[]>("/paper/journal"),
  performance: (cohort = "paper", grain = "overall") =>
    apiRequest<import("./types").PerformanceSnapshotOut[]>(
      `/analytics/performance?cohort=${encodeURIComponent(cohort)}&grain=${encodeURIComponent(grain)}`,
    ),
  refreshPerformance: (cohort = "paper") =>
    apiRequest<import("./types").PerformanceSnapshotOut[]>("/analytics/performance/refresh", {
      method: "POST",
      body: { cohort },
    }),
  narratePerformance: (snapshotId: string) =>
    apiRequest<{ snapshot_id: string; cohort: string; narrative: string }>(
      `/analytics/performance/${snapshotId}/narrate`,
      { method: "POST", body: {} },
    ),
  calibration: () =>
    apiRequest<import("./types").CalibrationSnapshotOut[]>("/analytics/calibration"),
  refreshCalibration: () =>
    apiRequest<import("./types").CalibrationSnapshotOut>("/analytics/calibration/refresh", {
      method: "POST",
      body: {},
    }),
  backtests: () => apiRequest<Array<Record<string, unknown>>>("/backtests/jobs"),
  telegramStatus: () => apiRequest<Record<string, unknown>>("/telegram/status"),
  uploadScreenshot: async (uri: string, name: string, type: string, caption?: string) => {
    const form = new FormData();
    form.append("file", { uri, name, type } as unknown as Blob);
    if (caption) {
      const parts = caption.trim().split(/\s+/);
      if (parts[0]) form.append("market_symbol", parts[0]);
      if (parts[1]) form.append("market_timeframe", parts[1]);
    }
    return apiRequest<Record<string, unknown>>("/vision/screenshots", { formData: form });
  },
};
