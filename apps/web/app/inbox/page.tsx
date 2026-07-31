"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ChangeEvent, useState } from "react";
import { AppShell, useSessionToken } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import {
  ApiError,
  DocumentStatus,
  getDocuments,
  uploadDocument,
} from "@/lib/api";
import { useQueryParam } from "@/lib/use-query-param";

const rupiah = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});
const processingStatuses: DocumentStatus[] = [
  "UPLOADED",
  "QUEUED",
  "EXTRACTING",
  "VALIDATING",
];

export default function InboxPage() {
  const token = useSessionToken();
  const queryClient = useQueryClient();
  const queryStatus = useQueryParam("status");
  const [statusOverride, setStatus] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const status = statusOverride ?? queryStatus ?? "";
  const documents = useQuery({
    queryKey: ["documents", status, search],
    queryFn: () => getDocuments(token!, { status, search }),
    enabled: Boolean(token),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => processingStatuses.includes(item.status))
        ? 2_000
        : false,
  });
  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(token!, file),
    onSuccess: (document) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      window.location.assign(`/inbox/${document.id}`);
    },
  });

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) upload.mutate(file);
  }

  const uploadError =
    upload.error instanceof ApiError ? upload.error.message : "Unggahan belum berhasil.";
  const items = documents.data?.items ?? [];
  const reviewCount = items.filter((item) =>
    ["NEEDS_REVIEW", "READY_TO_POST"].includes(item.status),
  ).length;
  const postedCount = items.filter((item) => item.status === "POSTED").length;

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-7 sm:px-8 sm:py-9 xl:px-10">
        <header className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
          <div>
            <p className="eyebrow text-[#8a6a51]">Alur pembukuan</p>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] sm:text-[28px]">
              Dokumen
            </h1>
            <p className="mt-1.5 text-sm text-[#69716c]">
              Receipt dan invoice yang masuk ke proses pembukuan.
            </p>
          </div>
          <label className="primary-button cursor-pointer self-start sm:self-auto">
            <UploadIcon />
            {upload.isPending ? "Mengunggah…" : "Unggah dokumen"}
            <input
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              className="sr-only"
              disabled={upload.isPending}
              onChange={handleFile}
              type="file"
            />
          </label>
        </header>

        <section
          aria-label="Ringkasan dokumen"
          className="app-card mt-7 grid overflow-hidden sm:grid-cols-3"
        >
          <SummaryItem label="Total dokumen" value={documents.data?.total ?? "—"} />
          <SummaryItem
            className="border-t sm:border-l sm:border-t-0"
            label="Perlu tindakan"
            value={reviewCount}
          />
          <SummaryItem
            className="border-t sm:border-l sm:border-t-0"
            label="Sudah dibukukan"
            value={postedCount}
          />
        </section>

        {upload.isError ? (
          <div
            className="mt-4 flex items-start gap-3 rounded-lg border border-[#e3b7af] bg-[#fbeeea] p-3.5 text-[#8d3a30]"
            role="alert"
          >
            <span className="font-semibold">Unggahan gagal.</span>
            <span className="text-sm">{uploadError}</span>
          </div>
        ) : null}

        <section className="app-card mt-5 overflow-hidden">
          <div className="flex flex-col gap-3 border-b bg-muted/40 p-3 sm:flex-row sm:items-center">
            <label className="relative flex-1">
              <SearchIcon />
              <span className="sr-only">Cari dokumen</span>
              <input
                className="form-control !pl-10"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Cari vendor, nomor, atau nama file"
                type="search"
                value={search}
              />
            </label>
            <label>
              <span className="sr-only">Filter status</span>
              <select
                className="form-control min-w-48"
                onChange={(event) => setStatus(event.target.value)}
                value={status}
              >
                <option value="">Semua status</option>
                <option value="NEEDS_REVIEW">Perlu ditinjau</option>
                <option value="READY_TO_POST">Siap dibukukan</option>
                <option value="POSTED">Sudah dibukukan</option>
                <option value="FAILED">Gagal</option>
              </select>
            </label>
          </div>

          {documents.isPending ? (
            <div className="grid min-h-64 place-items-center text-center" role="status">
              <div>
                <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#d7dad5] border-t-[#174d3a]" />
                <p className="mt-3 text-sm text-[#69716c]">Memuat dokumen…</p>
              </div>
            </div>
          ) : items.length ? (
            <div>
              <div className="hidden grid-cols-[minmax(250px,1.5fr)_minmax(140px,.65fr)_minmax(150px,.65fr)_145px_18px] gap-4 border-b bg-muted/55 px-4 py-2.5 text-[11px] font-medium text-muted-foreground lg:grid">
                <span>Dokumen</span>
                <span>Tanggal</span>
                <span className="text-right">Nominal</span>
                <span>Status</span>
                <span />
              </div>
              <div className="divide-y">
                {items.map((document) => (
                  <Link
                    className="group grid gap-3 px-4 py-3.5 transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/70 lg:grid-cols-[minmax(250px,1.5fr)_minmax(140px,.65fr)_minmax(150px,.65fr)_145px_18px] lg:items-center"
                    href={`/inbox/${document.id}`}
                    key={document.id}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border bg-muted text-muted-foreground">
                        <FileIcon type={document.mime_type} />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {document.vendor_name ?? document.original_filename}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-[#777e79]">
                          {document.document_number ?? document.original_filename}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center justify-between lg:block">
                      <span className="text-xs text-[#777e79] lg:hidden">Tanggal</span>
                      <p className="text-sm text-[#555e58]">
                        {document.transaction_date
                          ? new Date(document.transaction_date).toLocaleDateString(
                              "id-ID",
                              { day: "2-digit", month: "short", year: "numeric" },
                            )
                          : "Belum terbaca"}
                      </p>
                    </div>
                    <div className="flex items-center justify-between lg:block lg:text-right">
                      <span className="text-xs text-[#777e79] lg:hidden">Nominal</span>
                      <p className="tabular-nums text-sm font-medium">
                        {document.total
                          ? rupiah.format(Number(document.total))
                          : "Belum terbaca"}
                      </p>
                    </div>
                    <div>
                      <StatusBadge status={document.status} />
                    </div>
                    <span className="hidden text-[#9da29d] group-hover:text-[#174d3a] lg:block">
                      ›
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ) : (
            <div className="grid min-h-72 place-items-center p-8 text-center">
              <div>
                <span className="mx-auto grid h-11 w-11 place-items-center rounded-lg border border-[#dfd5c7] bg-[#f3ece2] text-[#58635d]">
                  <UploadIcon />
                </span>
                <p className="mt-4 text-sm font-semibold">Belum ada dokumen</p>
                <p className="mx-auto mt-1.5 max-w-sm text-sm leading-6 text-[#69716c]">
                  Unggah PDF, PNG, atau JPEG untuk menyiapkan draft jurnal.
                </p>
              </div>
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}

function SummaryItem({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string | number;
  className?: string;
}) {
  return (
    <div className={`border-border px-5 py-5 ${className}`}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="tabular-nums mt-1.5 text-2xl font-semibold tracking-[-0.035em]">
        {value}
      </p>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg
      aria-hidden="true"
      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#777e79]"
      fill="none"
      height="16"
      viewBox="0 0 24 24"
      width="16"
    >
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.7" />
      <path d="m16 16 4 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

function FileIcon({ type }: { type: string }) {
  return (
    <svg aria-hidden="true" fill="none" height="17" viewBox="0 0 24 24" width="17">
      <path d="M6 3h8l4 4v14H6z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M14 3v5h4M9 13h6M9 17h4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      {type.includes("pdf") ? <path d="M8 10h3" stroke="currentColor" strokeWidth="1.7" /> : null}
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 24 24" width="16">
      <path d="M12 16V4m0 0L7 9m5-5 5 5M5 15v5h14v-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}
