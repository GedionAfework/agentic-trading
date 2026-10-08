export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  roles: string[];
};

export type MeResponse = {
  id: string;
  email: string;
  display_name: string | null;
  roles: string[];
  status: string;
};

export type SessionOut = {
  id: string;
  device_name: string | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  current: boolean;
};

export type CandidateOut = {
  id: string;
  dedupe_key: string;
  strategy_code: string;
  strategy_version_no: number;
  instrument_symbol: string;
  timeframe: string;
  setup_anchor: string;
  signal_type: string;
  action: string;
  candle_open_time: string;
  decision_record_id: string | null;
  publish_state: string;
  seen_count: number;
  payload: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
};

export type PaperAccountOut = {
  account_id: string;
  label: string;
  currency: string;
  starting_equity: string;
  equity: string;
  fill_model: Record<string, unknown>;
  trades_by_status: Record<string, number>;
  closed_trades: number;
  sum_realized_r: string;
  soak: Record<string, unknown>;
  integrity: { ok: boolean; defects: string[] };
};

export type PaperTradeOut = {
  id: string;
  instrument_symbol: string;
  timeframe: string;
  direction: string;
  status: string;
  label: string;
  planned_entry: number;
  stop_price: number;
  target_price: number;
  entry_price: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  realized_r: number | null;
  realized_pnl: number | null;
  created_at: string;
  closed_at: string | null;
};

export type JournalEntryOut = {
  id: string;
  cohort: string;
  instrument_symbol: string;
  timeframe: string;
  direction: string;
  outcome: string;
  realized_r: number | null;
  realized_pnl: number | null;
  summary: string;
  details: Record<string, unknown>;
  paper_trade_id: string | null;
  created_at: string;
};

export type AskResponse = {
  answer: string;
  sufficient_evidence: boolean;
  confidence: string;
  citations: Array<{
    document_id: string;
    chunk_id: string;
    page: number | null;
    title: string;
    authority_tier: number;
    score: number | null;
  }>;
  conflicts: string[];
};

export type StrategyOut = {
  id: string;
  code: string;
  name: string;
  status: string;
  published_version_no?: number | null;
};

export type HealthOut = {
  status: string;
  service: string;
  env: string;
  version: string;
  checks?: Record<string, unknown>;
};

export type ScannerStatusOut = {
  scanner_version: string;
  switches: { scanner_enabled: boolean; notifications_enabled: boolean };
  candidates_total: number;
  candidates_published: number;
  dead_letters: number;
  provider?: Record<string, unknown>;
};

export type PerformanceSnapshotOut = {
  id: string;
  cohort: string;
  grain: string;
  strategy_code: string;
  instrument_symbol: string;
  timeframe: string;
  session_bucket: string;
  sample_size: number;
  sample_status: string;
  metrics: {
    trade_count?: number;
    win_count?: number;
    loss_count?: number;
    win_rate?: number | null;
    mean_r?: number | null;
    sum_r?: number | null;
    [key: string]: unknown;
  };
  warnings: string[];
  computed_at: string;
};

export type CalibrationSnapshotOut = {
  id: string;
  cohort: string;
  band_field: string;
  sample_size: number;
  sample_status: string;
  bands: Record<string, unknown>;
  drift_flags: string[];
  warnings: string[];
  computed_at: string;
};

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    correlation_id?: string;
    retryable?: boolean;
  };
  detail?: unknown;
};
