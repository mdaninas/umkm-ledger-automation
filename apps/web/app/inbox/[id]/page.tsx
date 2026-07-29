"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppShell, useSessionToken } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import {
  ApiError,
  DocumentDetail,
  DocumentReviewPayload,
  getAccounts,
  getDocument,
  getDocumentBlob,
  postDocument,
  retryDocument,
  reviewDocument,
} from "@/lib/api";

const processingStatuses = ["UPLOADED", "QUEUED", "EXTRACTING", "VALIDATING"];
const rupiah = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const token = useSessionToken();
  const queryClient = useQueryClient();
  const document = useQuery({
    queryKey: ["document", params.id],
    queryFn: () => getDocument(token!, params.id),
    enabled: Boolean(token && params.id),
    refetchInterval: (query) =>
      processingStatuses.includes(query.state.data?.status ?? "") ? 2_000 : false,
  });
  const retry = useMutation({
    mutationFn: () => retryDocument(token!, params.id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["document", params.id] }),
  });

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-7 sm:px-8 sm:py-9 xl:px-10">
        <Link
          className="inline-flex items-center gap-2 text-xs font-medium text-[#69716c] hover:text-[#174d3a]"
          href="/inbox"
        >
          <span aria-hidden="true">←</span>
          Dokumen
        </Link>
        {document.isPending ? (
          <p className="py-20 text-center" role="status">
            Memuat detail dan hasil ekstraksi…
          </p>
        ) : document.isError || !document.data ? (
          <div className="app-card mt-8 border-[#e8aa97] bg-[#fff3ef] p-6">
            <h1 className="text-xl font-semibold">Dokumen tidak dapat dibuka</h1>
            <p className="mt-2 text-[#8a321c]">Periksa akses Anda atau muat ulang halaman.</p>
          </div>
        ) : (
          <>
            <header className="mt-5 flex flex-col justify-between gap-5 border-b border-[#dedfdb] pb-6 md:flex-row md:items-end">
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="text-2xl font-semibold tracking-[-0.035em] sm:text-[28px]">
                    {document.data.vendor_name ?? document.data.original_filename}
                  </h1>
                  <StatusBadge status={document.data.status} />
                </div>
                <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#69716c]">
                  <span>{document.data.original_filename}</span>
                  <span>{document.data.document_number ?? "Nomor belum tersedia"}</span>
                  <span>{document.data.document_type.replaceAll("_", " ")}</span>
                </div>
              </div>
              {document.data.status === "FAILED" ? (
                <button
                  className="primary-button self-start md:self-auto"
                  disabled={retry.isPending}
                  onClick={() => retry.mutate()}
                  type="button"
                >
                  {retry.isPending ? "Menjadwalkan…" : "Coba proses lagi"}
                </button>
              ) : null}
            </header>

            {document.data.duplicate_of_id ? (
              <div className="mt-4 flex items-start gap-3 rounded-lg border border-[#e3cf9f] bg-[#faf4e6] p-3.5">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-[#a77721] text-xs font-semibold text-white">
                  !
                </span>
                <p className="text-sm leading-6">
                  <strong>Kemungkinan duplikat terdeteksi.</strong>{" "}
                  <span className="text-[#735415]">
                  {document.data.duplicate_reason === "EXACT_FILE"
                    ? "Isi file sama persis dengan dokumen sebelumnya."
                    : "Vendor, nomor, tanggal, dan total sama dengan dokumen sebelumnya."}
                </span>
                </p>
              </div>
            ) : null}

            <section className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(460px,0.88fr)]">
              <DocumentPreview
                document={document.data}
                id={params.id}
                token={token!}
              />
              <ReviewPanel
                document={document.data}
                onUpdated={(updated) => {
                  queryClient.setQueryData(["document", params.id], updated);
                  queryClient.invalidateQueries({ queryKey: ["documents"] });
                  queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
                }}
                token={token!}
              />
            </section>

            <section className="mt-4 grid gap-4 lg:grid-cols-2">
              <WorkflowCard document={document.data} />
              <AuditCard document={document.data} />
            </section>
          </>
        )}
      </main>
    </AppShell>
  );
}

function DocumentPreview({
  document,
  id,
  token,
}: {
  document: DocumentDetail;
  id: string;
  token: string;
}) {
  const blob = useQuery({
    queryKey: ["document-content", id],
    queryFn: () => getDocumentBlob(token, id),
  });
  const url = useMemo(
    () => (blob.data ? URL.createObjectURL(blob.data) : null),
    [blob.data],
  );
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  return (
    <article className="app-card overflow-hidden !bg-[#eeefec] xl:sticky xl:top-6 xl:self-start">
      <div className="flex items-center justify-between border-b border-[#dedfdb] bg-white px-4 py-3.5">
        <div>
          <p className="text-sm font-semibold">Dokumen asli</p>
          <p className="mt-0.5 text-[11px] text-[#777e79]">
            Pratinjau privat · hanya untuk workspace ini
          </p>
        </div>
        <span className="rounded-md border border-[#dfd5c7] bg-[#f3eee5] px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-[#69716c]">
          {document.mime_type.replace("application/", "")}
        </span>
      </div>
      <div className="grid min-h-[620px] place-items-center p-3 sm:p-4">
        {!url ? (
          <div className="text-center">
            <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#d1d4cf] border-t-[#174d3a]" />
            <p className="mt-3 text-sm text-[#69716c]">Memuat pratinjau…</p>
          </div>
        ) : document.mime_type === "application/pdf" ? (
          <object
            aria-label={`Pratinjau ${document.original_filename}`}
            className="h-[620px] w-full rounded-md bg-white"
            data={url}
            type="application/pdf"
          >
            <a href={url}>Buka dokumen PDF</a>
          </object>
        ) : (
          // The source is a private, short-lived object URL created from an authenticated fetch.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            alt={`Pratinjau ${document.original_filename}`}
            className="max-h-[620px] rounded-md object-contain"
            src={url}
          />
        )}
      </div>
    </article>
  );
}

function ReviewPanel({
  document,
  token,
  onUpdated,
}: {
  document: DocumentDetail;
  token: string;
  onUpdated: (document: DocumentDetail) => void;
}) {
  const accounts = useQuery({
    queryKey: ["ledger-accounts"],
    queryFn: () => getAccounts(token),
  });
  const [form, setForm] = useState<DocumentReviewPayload>({
    document_type: document.document_type,
    document_number: document.document_number,
    vendor_name: document.vendor_name,
    transaction_date: document.transaction_date,
    due_date: document.due_date,
    currency: document.currency,
    subtotal: document.subtotal,
    tax: document.tax,
    total: document.total,
    payment_method: document.payment_method,
    final_account_id: document.final_account?.id ?? document.proposed_account?.id ?? null,
    review_comment: "",
  });
  const review = useMutation({
    mutationFn: (payload: Partial<DocumentReviewPayload>) =>
      reviewDocument(token, document.id, payload),
    onSuccess: onUpdated,
  });
  const post = useMutation({
    mutationFn: () => postDocument(token, document.id, form.review_comment ?? ""),
    onSuccess: onUpdated,
  });

  function update(field: keyof DocumentReviewPayload, value: string | null) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    review.mutate(form);
  }

  const error = review.error ?? post.error;
  const errorMessage =
    error instanceof ApiError ? error.message : error ? "Tindakan belum berhasil." : null;
  const canReview = !["POSTED", "REJECTED", "FAILED"].includes(document.status);

  return (
    <div className="space-y-5">
      <article className="app-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold tracking-[-0.015em]">
              Hasil ekstraksi
            </h2>
            <p className="mt-1 text-xs text-[#777e79]">
              {document.latest_extraction
                ? `${document.latest_extraction.provider} · ${document.latest_extraction.model} · ${document.latest_extraction.latency_ms} ms`
                : "Menunggu hasil ekstraksi"}
            </p>
          </div>
          {document.extraction_confidence ? (
            <span className="rounded-md bg-[#e8f3ed] px-2 py-1 text-[11px] font-medium text-[#176846]">
              {Math.round(Number(document.extraction_confidence) * 100)}% confidence
            </span>
          ) : null}
        </div>

        {document.validation_errors.length || document.validation_warnings.length ? (
          <div className="mt-5 space-y-2">
            {[...document.validation_errors, ...document.validation_warnings].map(
              (issue, index) => (
                <p
                  className="rounded-lg border border-[#e3cf9f] bg-[#faf4e6] px-3 py-2 text-sm text-[#735415]"
                  key={`${issue.code}-${index}`}
                >
                  {issue.message}
                </p>
              ),
            )}
          </div>
        ) : null}

        <form className="mt-5 grid gap-x-4 gap-y-4 sm:grid-cols-2" onSubmit={submit}>
          <Field label="Jenis dokumen">
            <select
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("document_type", event.target.value)}
              value={form.document_type}
            >
              <option value="RECEIPT">Receipt</option>
              <option value="SUPPLIER_INVOICE">Supplier invoice</option>
              <option value="CUSTOMER_INVOICE">Customer invoice</option>
              <option value="UNKNOWN">Unknown</option>
            </select>
          </Field>
          <Field label="Nomor dokumen">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("document_number", event.target.value)}
              value={form.document_number ?? ""}
            />
          </Field>
          <Field label="Vendor">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("vendor_name", event.target.value)}
              value={form.vendor_name ?? ""}
            />
          </Field>
          <Field label="Tanggal transaksi">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("transaction_date", event.target.value || null)}
              type="date"
              value={form.transaction_date ?? ""}
            />
          </Field>
          <Field label="Subtotal">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("subtotal", event.target.value)}
              type="number"
              value={form.subtotal ?? ""}
            />
          </Field>
          <Field label="Pajak">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("tax", event.target.value)}
              type="number"
              value={form.tax ?? ""}
            />
          </Field>
          <Field label="Total">
            <input
              className="form-control"
              disabled={!canReview}
              min="0"
              onChange={(event) => update("total", event.target.value)}
              required
              type="number"
              value={form.total ?? ""}
            />
          </Field>
          <Field label="Metode pembayaran">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("payment_method", event.target.value)}
              value={form.payment_method ?? ""}
            />
          </Field>
          <Field label="Kategori akun">
            <select
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("final_account_id", event.target.value)}
              required
              value={form.final_account_id ?? ""}
            >
              <option value="">Pilih akun</option>
              {accounts.data?.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.code} · {account.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Catatan review">
            <input
              className="form-control"
              disabled={!canReview}
              onChange={(event) => update("review_comment", event.target.value)}
              value={form.review_comment ?? ""}
            />
          </Field>

          {errorMessage ? (
            <p className="sm:col-span-2 text-sm text-[#8a321c]" role="alert">
              {errorMessage}
            </p>
          ) : null}

          {document.duplicate_of_id && canReview ? (
            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <button
                className="secondary-button"
                onClick={() =>
                  review.mutate({
                    duplicate_decision: "DUPLICATE",
                    review_comment: "Confirmed duplicate",
                  })
                }
                type="button"
              >
                Tandai sebagai duplikat
              </button>
              <button
                className="primary-button"
                onClick={() =>
                  review.mutate({ ...form, duplicate_decision: "DIFFERENT_TRANSACTION" })
                }
                type="button"
              >
                Ini transaksi berbeda
              </button>
            </div>
          ) : canReview ? (
            <button
              className="primary-button sm:col-span-2"
              disabled={review.isPending}
              type="submit"
            >
              {review.isPending ? "Menyimpan…" : "Simpan review dan siapkan posting"}
            </button>
          ) : null}
        </form>
      </article>

      {document.journal ? (
        <article className="app-card overflow-hidden">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">
                  Jurnal {document.journal.status}
                </h2>
                <p className="mt-1 text-sm text-[#69716c]">
                  {document.journal.description}
                </p>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium ${
                  document.journal.balanced
                    ? "bg-[#e8f3ed] text-[#176846]"
                    : "bg-[#f8eae7] text-[#963d32]"
                }`}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                {document.journal.balanced ? "Seimbang" : "Tidak seimbang"}
              </span>
            </div>
            <div className="mt-5 overflow-x-auto rounded-lg border border-[#dfd5c7]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#f8f2e9] text-[10px] font-medium text-[#777e79]">
                  <tr>
                    <th className="px-3 py-2.5">Akun</th>
                    <th className="px-3 py-2.5 text-right">Debit</th>
                    <th className="px-3 py-2.5 text-right">Kredit</th>
                  </tr>
                </thead>
                <tbody>
                  {document.journal.lines.map((line) => (
                    <tr className="border-t border-[#eadfd2]" key={line.id}>
                      <td className="px-3 py-3">
                        {line.account.code} · {line.account.name}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {rupiah.format(Number(line.debit))}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {rupiah.format(Number(line.credit))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {document.status === "READY_TO_POST" ? (
            <div className="border-t border-[#e4dacd] bg-[#f8f2e9] p-4">
              <button
                className="primary-button w-full"
                disabled={post.isPending || !document.journal.balanced}
                onClick={() => post.mutate()}
                type="button"
              >
                {post.isPending ? "Membukukan…" : "Setujui dan posting jurnal"}
              </button>
            </div>
          ) : null}
        </article>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-[#4d5550]">{label}</span>
      {children}
    </label>
  );
}

function WorkflowCard({ document }: { document: DocumentDetail }) {
  return (
    <article className="app-card p-5">
      <h2 className="text-base font-semibold">Workflow</h2>
      <p className="mt-1 truncate text-xs text-[#777e79]">
        ID: {document.latest_workflow?.correlation_id ?? "—"}
      </p>
      <ol className="mt-4 divide-y divide-[#eadfd2] border-t border-[#eadfd2]">
        {document.latest_workflow?.steps.map((step) => (
          <li
            className="flex items-center justify-between gap-4 py-3 text-sm"
            key={step.id}
          >
            <span className="flex items-center gap-2.5 capitalize">
              <span
                className={`h-2 w-2 rounded-full ${
                  step.status === "SUCCEEDED"
                    ? "bg-[#20a66f]"
                    : step.status === "FAILED"
                      ? "bg-[#c9593f]"
                      : "bg-[#d59b29]"
                }`}
              />
              {step.step_name.replaceAll("_", " ")}
            </span>
            <span className="text-[10px] font-medium tracking-wide text-[#777e79]">
              {step.status}
            </span>
          </li>
        )) ?? <li className="text-sm text-[#65716b]">Workflow belum dimulai.</li>}
      </ol>
    </article>
  );
}

function AuditCard({ document }: { document: DocumentDetail }) {
  return (
    <article className="app-card p-5">
      <h2 className="text-base font-semibold">Audit timeline</h2>
      <ol className="mt-4 max-h-[390px] space-y-0 overflow-y-auto pr-2">
        {document.audit_timeline.map((event) => (
          <li
            className="relative border-l border-[#d7dad5] pb-5 pl-5 last:pb-0"
            key={event.id}
          >
            <span className="absolute -left-[4px] top-1 h-2 w-2 rounded-full border border-white bg-[#6a8f7d]" />
            <p className="text-sm font-medium">
              {event.action.replaceAll(".", " · ")}
            </p>
            <p className="mt-1 text-xs text-[#777e79]">
              {new Date(event.created_at).toLocaleString("id-ID")} · {event.actor_type}
            </p>
          </li>
        ))}
      </ol>
    </article>
  );
}
