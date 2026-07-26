"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AppShell, useSessionToken } from "@/components/app-shell";
import { Approval, getApprovals } from "@/lib/api";

export default function ApprovalsPage() {
  const token = useSessionToken();
  const approvals = useQuery({
    queryKey: ["approvals"],
    queryFn: () => getApprovals(token!),
    enabled: Boolean(token),
    refetchInterval: 10_000,
  });
  const items = approvals.data ?? [];
  const pending = items.filter((item) => item.status === "PENDING").length;
  const approved = items.filter((item) => item.status === "APPROVED").length;
  const rejected = items.filter((item) => item.status === "REJECTED").length;

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-7 sm:px-8 sm:py-9 xl:px-10">
        <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] sm:text-[28px]">
              Approval
            </h1>
            <p className="mt-1.5 text-sm text-[#69716c]">
              Keputusan yang membutuhkan konfirmasi sebelum dicatat.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-[#69716c]">
            <span className="status-dot text-[#2d9169]" />
            Diperbarui otomatis
          </div>
        </header>

        <section className="app-card mt-7 grid overflow-hidden sm:grid-cols-3">
          <ApprovalStat label="Menunggu" value={pending} />
          <ApprovalStat
            className="border-t sm:border-l sm:border-t-0"
            label="Disetujui"
            value={approved}
          />
          <ApprovalStat
            className="border-t sm:border-l sm:border-t-0"
            label="Ditolak"
            value={rejected}
          />
        </section>

        <section className="app-card mt-5 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[#e3e4e1] px-4 py-3.5 sm:px-5">
            <div>
              <h2 className="text-sm font-semibold">Riwayat keputusan</h2>
              <p className="mt-0.5 text-xs text-[#777e79]">
                {items.length} permintaan
              </p>
            </div>
            <ShieldIcon />
          </div>

          {approvals.isPending ? (
            <div className="grid min-h-64 place-items-center" role="status">
              <div className="text-center">
                <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#d7dad5] border-t-[#174d3a]" />
                <p className="mt-3 text-sm text-[#69716c]">Memuat approval…</p>
              </div>
            </div>
          ) : items.length ? (
            <>
              <div className="hidden grid-cols-[minmax(280px,1fr)_140px_170px_115px_18px] gap-4 border-b border-[#e3e4e1] bg-[#fafaf8] px-4 py-2.5 text-[11px] font-medium text-[#777e79] md:grid">
                <span>Permintaan</span>
                <span>Risiko</span>
                <span>Waktu</span>
                <span>Status</span>
                <span />
              </div>
              <div className="divide-y divide-[#e6e7e4]">
                {items.map((approval) => (
                  <ApprovalRow approval={approval} key={approval.id} />
                ))}
              </div>
            </>
          ) : (
            <div className="grid min-h-72 place-items-center p-8 text-center">
              <div>
                <span className="mx-auto grid h-11 w-11 place-items-center rounded-lg border border-[#dfe1dd] bg-[#f4f5f2] text-[#58635d]">
                  <ShieldIcon />
                </span>
                <p className="mt-4 text-sm font-semibold">Tidak ada approval</p>
                <p className="mx-auto mt-1.5 max-w-sm text-sm leading-6 text-[#69716c]">
                  Dokumen yang selesai direview akan muncul di sini.
                </p>
              </div>
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}

function ApprovalRow({ approval }: { approval: Approval }) {
  return (
    <Link
      className="group grid gap-3 px-4 py-4 transition hover:bg-[#fafbf9] md:grid-cols-[minmax(280px,1fr)_140px_170px_115px_18px] md:items-center"
      href={`/inbox/${approval.document_id}`}
    >
      <div className="min-w-0">
        <p className="text-sm font-medium">Posting jurnal dokumen</p>
        <p className="mt-0.5 truncate text-xs text-[#69716c]">{approval.reason}</p>
      </div>
      <div>
        <span className="rounded-md bg-[#f0f1ee] px-2 py-1 text-[11px] font-medium capitalize text-[#606863]">
          {approval.risk_level.toLowerCase()}
        </span>
      </div>
      <p className="text-xs text-[#69716c]">
        {new Date(approval.requested_at).toLocaleString("id-ID", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </p>
      <ApprovalStatus status={approval.status} />
      <span className="hidden text-[#9da29d] group-hover:text-[#174d3a] md:block">
        ›
      </span>
    </Link>
  );
}

function ApprovalStatus({ status }: { status: Approval["status"] }) {
  const style =
    status === "APPROVED"
      ? "bg-[#e8f3ed] text-[#176846]"
      : status === "REJECTED"
        ? "bg-[#f8eae7] text-[#963d32]"
        : "bg-[#f8f0df] text-[#805b18]";
  const label =
    status === "APPROVED"
      ? "Disetujui"
      : status === "REJECTED"
        ? "Ditolak"
        : status === "PENDING"
          ? "Menunggu"
          : status;
  return (
    <span className={`w-fit rounded-md px-2 py-1 text-[11px] font-medium ${style}`}>
      {label}
    </span>
  );
}

function ApprovalStat({
  label,
  value,
  className = "",
}: {
  label: string;
  value: number;
  className?: string;
}) {
  return (
    <div className={`border-[#e3e4e1] px-5 py-4 ${className}`}>
      <p className="text-xs text-[#69716c]">{label}</p>
      <p className="tabular-nums mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function ShieldIcon() {
  return (
    <svg aria-hidden="true" className="text-[#69716c]" fill="none" height="18" viewBox="0 0 24 24" width="18">
      <path d="M12 3 5 6v5c0 4.6 2.9 8.7 7 10 4.1-1.3 7-5.4 7-10V6l-7-3Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="m9 12 2 2 4-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}
