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
  document_id: string | null;
  entity_type: "DOCUMENT" | "INVOICE_REMINDER";
  entity_id: string;
  journal_entry_id: string | null;
  action_type: string;
  reason: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED";
  requested_at: string;
  decision_comment: string | null;
}

export type InvoiceStatus = "OUTSTANDING" | "DUE_SOON" | "OVERDUE" | "PAID";
export type ReminderStatus =
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "QUEUED"
  | "SENT"
  | "FAILED";

export interface Customer {
  id: string;
  name: string;
  email: string;
  phone_masked: string | null;
}

export interface OutboxMessage {
  id: string;
  channel: "EMAIL";
  recipient_masked: string;
  template: string;
  status: "PENDING" | "PROCESSING" | "SENT" | "FAILED";
  attempt_count: number;
  next_attempt_at: string | null;
  last_error: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface InvoiceReminder {
  id: string;
  invoice_id: string;
  sequence: number;
  subject: string;
  body: string;
  source: "AI_ASSISTED" | "DETERMINISTIC_FALLBACK";
  status: ReminderStatus;
  approval_id: string | null;
  approval_status: Approval["status"] | null;
  decision_comment: string | null;
  approved_at: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
  outbox: OutboxMessage | null;
}

export interface InvoiceSummary {
  id: string;
  invoice_number: string;
  customer: Customer;
  issue_date: string;
  due_date: string;
  subtotal: string;
  tax: string;
  total: string;
  currency: string;
  status: InvoiceStatus;
  paid_at: string | null;
  days_until_due: number;
  latest_reminder_status: ReminderStatus | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceDetail extends InvoiceSummary {
  reminders: InvoiceReminder[];
  audit_timeline: Array<{
    id: string;
    actor_type: string;
    action: string;
    entity_type: string;
    entity_id: string;
    correlation_id: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
}

export interface InvoiceList {
  items: InvoiceSummary[];
  total: number;
  counts: {
    total: number;
    outstanding: number;
    due_soon: number;
    overdue: number;
    paid: number;
    outstanding_amount: string;
  };
  as_of: string;
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

export type BankTransactionStatus =
  | "UNMATCHED"
  | "SUGGESTED"
  | "AUTO_MATCHED"
  | "CONFIRMED";

export type ReconciliationStatus =
  | "SUGGESTED"
  | "AUTO_MATCHED"
  | "CONFIRMED"
  | "REJECTED";

export interface BankColumnMapping {
  date: string;
  description: string;
  amount?: string;
  debit?: string;
  credit?: string;
  reference?: string;
  date_format?: string;
}

export interface BankImport {
  id: string;
  filename: string;
  sha256: string;
  column_mapping: Record<string, string>;
  status: "COMPLETED" | "COMPLETED_WITH_ERRORS";
  row_count: number;
  imported_count: number;
  duplicate_count: number;
  error_count: number;
  row_errors: Array<{ row: number; code: string; message: string }>;
  created_at: string;
  duplicate_file: boolean;
}

export interface ScoreComponent {
  score: string;
  max_score: string;
  explanation: string;
}

export interface ReconciliationCandidate {
  id: string;
  bank_transaction_id: string;
  source_type: "DOCUMENT";
  source: {
    id: string;
    document_type: DocumentType;
    document_number: string | null;
    vendor_name: string | null;
    transaction_date: string | null;
    total: string | null;
    currency: string;
    status: DocumentStatus;
  };
  score: string;
  score_breakdown: {
    amount: ScoreComponent;
    date: ScoreComponent;
    vendor: ScoreComponent;
    reference: ScoreComponent;
    policy: {
      review_threshold: string;
      auto_match_threshold: string;
      auto_match_eligible: boolean;
      conflicts: string[];
    };
  };
  status: ReconciliationStatus;
  decided_by: string | null;
  decision_comment: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface BankTransaction {
  id: string;
  bank_import_id: string;
  row_number: number;
  transaction_date: string;
  description: string;
  amount: string;
  direction: "DEBIT" | "CREDIT";
  reference: string | null;
  status: BankTransactionStatus;
  created_at: string;
  candidates: ReconciliationCandidate[];
}

export interface BankTransactionList {
  items: BankTransaction[];
  total: number;
  counts: {
    total: number;
    unmatched: number;
    suggested: number;
    matched: number;
  };
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

export function getInvoices(
  token: string,
  filters: { status?: string; search?: string } = {},
): Promise<InvoiceList> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);
  const query = params.size ? `?${params.toString()}` : "";
  return apiRequest(`/api/v1/invoices${query}`, {}, token);
}

export function getInvoice(token: string, id: string): Promise<InvoiceDetail> {
  return apiRequest(`/api/v1/invoices/${id}`, {}, token);
}

export function runInvoiceScheduler(
  token: string,
  asOf: string,
  forceFallback = false,
): Promise<{
  as_of: string;
  businesses_scanned: number;
  invoices_scanned: number;
  status_updates: number;
  drafts_created: number;
  fallback_drafts: number;
}> {
  return apiRequest(
    "/api/v1/invoices/scheduler/run",
    {
      method: "POST",
      body: JSON.stringify({
        as_of: asOf || null,
        force_fallback: forceFallback,
      }),
    },
    token,
  );
}

export function createInvoiceReminder(
  token: string,
  invoiceId: string,
  forceFallback = false,
): Promise<InvoiceReminder> {
  return apiRequest(
    `/api/v1/invoices/${invoiceId}/reminder-draft`,
    {
      method: "POST",
      body: JSON.stringify({ force_fallback: forceFallback }),
    },
    token,
  );
}

export function updateInvoiceReminder(
  token: string,
  reminderId: string,
  subject: string,
  body: string,
): Promise<InvoiceReminder> {
  return apiRequest(
    `/api/v1/invoice-reminders/${reminderId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ subject, body }),
    },
    token,
  );
}

export function approveInvoiceReminder(
  token: string,
  reminderId: string,
  comment: string,
): Promise<InvoiceDetail> {
  return apiRequest(
    `/api/v1/invoice-reminders/${reminderId}/approve`,
    {
      method: "POST",
      body: JSON.stringify({ comment: comment || null }),
      headers: { "Idempotency-Key": `approve-reminder-${reminderId}` },
    },
    token,
  );
}

export function rejectInvoiceReminder(
  token: string,
  reminderId: string,
  comment: string,
): Promise<InvoiceDetail> {
  return apiRequest(
    `/api/v1/invoice-reminders/${reminderId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ comment }),
    },
    token,
  );
}

export function retryOutboxMessage(
  token: string,
  outboxId: string,
): Promise<OutboxMessage> {
  return apiRequest(
    `/api/v1/outbox-messages/${outboxId}/retry`,
    { method: "POST" },
    token,
  );
}

export function getDashboardSummary(token: string): Promise<DashboardSummary> {
  return apiRequest("/api/v1/dashboard/summary", {}, token);
}

export function getBankImports(
  token: string,
): Promise<{ items: BankImport[]; total: number }> {
  return apiRequest("/api/v1/bank-imports", {}, token);
}

export function getBankTransactions(
  token: string,
  filters: { status?: string; search?: string } = {},
): Promise<BankTransactionList> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);
  const query = params.size ? `?${params.toString()}` : "";
  return apiRequest(`/api/v1/bank-transactions${query}`, {}, token);
}

export function uploadBankImport(
  token: string,
  file: File,
  mapping: BankColumnMapping,
): Promise<BankImport> {
  const body = new FormData();
  body.append("file", file);
  body.append("mapping", JSON.stringify(mapping));
  return apiRequest(
    "/api/v1/bank-imports",
    { method: "POST", body },
    token,
  );
}

export function confirmReconciliation(
  token: string,
  id: string,
  comment: string,
): Promise<ReconciliationCandidate> {
  return apiRequest(
    `/api/v1/reconciliations/${id}/confirm`,
    { method: "POST", body: JSON.stringify({ comment: comment || null }) },
    token,
  );
}

export function rejectReconciliation(
  token: string,
  id: string,
  comment: string,
): Promise<ReconciliationCandidate> {
  return apiRequest(
    `/api/v1/reconciliations/${id}/reject`,
    { method: "POST", body: JSON.stringify({ comment }) },
    token,
  );
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
