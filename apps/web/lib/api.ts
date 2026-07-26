export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export type Role = "owner" | "staff";

export interface UserSummary {
  id: string;
  email: string;
  display_name: string;
}

export interface BusinessSummary {
  id: string;
  name: string;
  timezone: string;
  currency: string;
}

export interface SessionProfile {
  user: UserSummary;
  business: BusinessSummary;
  role: Role;
}

export interface LoginResponse extends SessionProfile {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface HealthComponent {
  status: "healthy" | "unhealthy" | "skipped";
  latency_ms: number | null;
  detail: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded";
  service: string;
  environment: string;
  timestamp: string;
  components: Record<string, HealthComponent>;
}

export type DocumentStatus =
  | "UPLOADED"
  | "QUEUED"
  | "EXTRACTING"
  | "VALIDATING"
  | "NEEDS_REVIEW"
  | "READY_TO_POST"
  | "REJECTED"
  | "FAILED"
  | "POSTED"
  | "ARCHIVED";

export type DocumentType =
  | "RECEIPT"
  | "SUPPLIER_INVOICE"
  | "CUSTOMER_INVOICE"
  | "BANK_STATEMENT"
  | "UNKNOWN";

export interface LedgerAccount {
  id: string;
  code: string;
  name: string;
  account_type: "ASSET" | "LIABILITY" | "EQUITY" | "REVENUE" | "EXPENSE";
}

export interface DocumentSummary {
  id: string;
  source: "UPLOAD" | "DEMO";
  original_filename: string;
  mime_type: string;
  status: DocumentStatus;
  document_type: DocumentType;
  document_number: string | null;
  vendor_name: string | null;
  transaction_date: string | null;
  currency: string;
  total: string | null;
  extraction_confidence: string | null;
  duplicate_of_id: string | null;
  duplicate_reason: string | null;
  review_reason: string | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStep {
  id: string;
  step_name: string;
  sequence: number;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "SKIPPED";
  output_summary: Record<string, unknown>;
  error_code: string | null;
}

export interface JournalLine {
  id: string;
  account: LedgerAccount;
  debit: string;
  credit: string;
  memo: string | null;
}

export interface JournalEntry {
  id: string;
  status: "DRAFT" | "POSTED" | "REVERSED";
  entry_date: string;
  description: string;
  posted_at: string | null;
  lines: JournalLine[];
  total_debit: string;
  total_credit: string;
  balanced: boolean;
}

export interface Approval {
  id: string;
  document_id: string;
  journal_entry_id: string | null;
  action_type: string;
  reason: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED";
  requested_at: string;
  decision_comment: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  sha256: string;
  due_date: string | null;
  subtotal: string | null;
  tax: string | null;
  payment_method: string | null;
  validation_errors: Array<{ code: string; field: string | null; message: string }>;
  validation_warnings: Array<{ code: string; field: string | null; message: string }>;
  proposed_account: LedgerAccount | null;
  final_account: LedgerAccount | null;
  latest_extraction: {
    provider: string;
    model: string;
    field_confidences: Record<string, number>;
    warnings: string[];
    latency_ms: number;
  } | null;
  latest_workflow: {
    id: string;
    status: string;
    correlation_id: string;
    steps: WorkflowStep[];
  } | null;
  journal: JournalEntry | null;
  approval: Approval | null;
  audit_timeline: Array<{
    id: string;
    actor_type: string;
    action: string;
    correlation_id: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
}

export interface DashboardSummary {
  posted_journal_count: number;
  draft_journal_count: number;
  needs_review_count: number;
  posted_income: string;
  posted_expenses: string;
  cash_balance: string;
  bank_balance: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | { message?: string };
    } | null;
    const detail =
      typeof body?.detail === "string" ? body.detail : body?.detail?.message;
    throw new ApiError(
      detail ?? "Layanan tidak merespons dengan benar. Silakan coba lagi.",
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getProfile(token: string): Promise<SessionProfile> {
  return apiRequest<SessionProfile>("/api/v1/auth/me", {}, token);
}

export function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/v1/health");
}

export function getDocuments(
  token: string,
  filters: { status?: string; search?: string } = {},
): Promise<{ items: DocumentSummary[]; total: number }> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);
  const query = params.size ? `?${params.toString()}` : "";
  return apiRequest(`/api/v1/documents${query}`, {}, token);
}

export function getDocument(token: string, id: string): Promise<DocumentDetail> {
  return apiRequest(`/api/v1/documents/${id}`, {}, token);
}

export function uploadDocument(
  token: string,
  file: File,
): Promise<DocumentSummary> {
  const body = new FormData();
  body.append("file", file);
  return apiRequest(
    "/api/v1/documents",
    {
      method: "POST",
      body,
      headers: { "Idempotency-Key": crypto.randomUUID() },
    },
    token,
  );
}

export function getAccounts(token: string): Promise<LedgerAccount[]> {
  return apiRequest("/api/v1/accounts", {}, token);
}

export interface DocumentReviewPayload {
  document_type: DocumentType;
  document_number: string | null;
  vendor_name: string | null;
  transaction_date: string | null;
  due_date: string | null;
  currency: string;
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  payment_method: string | null;
  final_account_id: string | null;
  duplicate_decision?: "DUPLICATE" | "DIFFERENT_TRANSACTION";
  review_comment?: string;
}

export function reviewDocument(
  token: string,
  id: string,
  payload: Partial<DocumentReviewPayload>,
): Promise<DocumentDetail> {
  return apiRequest(
    `/api/v1/documents/${id}/review`,
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function postDocument(
  token: string,
  id: string,
  comment: string,
): Promise<DocumentDetail> {
  return apiRequest(
    `/api/v1/documents/${id}/post`,
    {
      method: "POST",
      body: JSON.stringify({ comment }),
      headers: { "Idempotency-Key": `post-${id}` },
    },
    token,
  );
}

export function retryDocument(token: string, id: string): Promise<DocumentSummary> {
  return apiRequest(`/api/v1/documents/${id}/retry`, { method: "POST" }, token);
}

export function getApprovals(token: string): Promise<Approval[]> {
  return apiRequest("/api/v1/approvals", {}, token);
}

export function getDashboardSummary(token: string): Promise<DashboardSummary> {
  return apiRequest("/api/v1/dashboard/summary", {}, token);
}

export async function getDocumentBlob(token: string, id: string): Promise<Blob> {
  const response = await fetch(`${API_URL}/api/v1/documents/${id}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new ApiError("Pratinjau dokumen tidak dapat dimuat.", response.status);
  }
  return response.blob();
}

export const sessionStorage = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem("umkm_access_token");
  },
  setToken(token: string): void {
    window.localStorage.setItem("umkm_access_token", token);
    window.dispatchEvent(new Event("umkm-session"));
  },
  clear(): void {
    window.localStorage.removeItem("umkm_access_token");
    window.dispatchEvent(new Event("umkm-session"));
  },
};
