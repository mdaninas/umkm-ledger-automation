"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell, useSessionToken } from "@/components/app-shell";
import {
  ApiError,
  InvoiceDetail,
  InvoiceReminder,
  InvoiceStatus,
  approveInvoiceReminder,
  createInvoiceReminder,
  getInvoice,
  getInvoices,
  rejectInvoiceReminder,
  retryOutboxMessage,
  runInvoiceScheduler,
  updateInvoiceReminder,
} from "@/lib/api";

const statusLabels: Record<InvoiceStatus, string> = {
  OUTSTANDING: "Belum dibayar",
  DUE_SOON: "Segera jatuh tempo",
  OVERDUE: "Terlambat",
  PAID: "Lunas",
};

export default function InvoicesPage() {
  const token = useSessionToken();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [asOf, setAsOf] = useState("");
  const [schedulerMessage, setSchedulerMessage] = useState<string | null>(null);

  const invoices = useQuery({
    queryKey: ["invoices", status, search],
    queryFn: () => getInvoices(token!, { status, search }),
    enabled: Boolean(token),
    refetchInterval: 10_000,
  });
  const items = invoices.data?.items ?? [];
  const effectiveAsOf = asOf || invoices.data?.as_of || "";
  const activeInvoiceId = selectedInvoiceId ?? items[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["invoice", activeInvoiceId],
    queryFn: () => getInvoice(token!, activeInvoiceId!),
    enabled: Boolean(token && activeInvoiceId),
    refetchInterval: 8_000,
  });

  async function refresh(invoiceId?: string) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["invoices"] }),
      queryClient.invalidateQueries({
        queryKey: ["invoice", invoiceId ?? activeInvoiceId],
      }),
      queryClient.invalidateQueries({ queryKey: ["approvals"] }),
    ]);
  }

  const scheduler = useMutation({
    mutationFn: () => runInvoiceScheduler(token!, effectiveAsOf),
    onSuccess: async (result) => {
      setSchedulerMessage(
        `${result.status_updates} status diperbarui · ${result.drafts_created} draft dibuat`,
      );
      await refresh();
    },
  });

  return (
    <AppShell>
      <main className="mx-auto max-w-[1320px] px-4 py-7 sm:px-7 sm:py-9 xl:px-9">
        <header className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <p className="eyebrow text-[#8a6a51]">Collection desk</p>
            <h1 className="text-2xl font-semibold tracking-[-0.035em] sm:text-[30px]">
              Piutang pelanggan
            </h1>
            <p className="mt-1.5 max-w-2xl text-sm leading-6 text-[#69716c]">
              Pantau jatuh tempo, tinjau pesan, dan tetap pegang keputusan sebelum
              pengingat keluar.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="grid gap-1.5 text-xs font-medium text-[#606a64]">
              Tanggal pemeriksaan
              <input
                className="h-10 rounded-lg border border-[#d8cbbb] bg-[#fffdfa] px-3 text-sm text-[#17241f] outline-none focus:border-[#527c6b]"
                onChange={(event) => setAsOf(event.target.value)}
                type="date"
                value={effectiveAsOf}
              />
            </label>
            <button
              className="primary-button h-10 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={scheduler.isPending || !effectiveAsOf}
              onClick={() => scheduler.mutate()}
              type="button"
            >
              {scheduler.isPending ? "Memeriksa…" : "Jalankan pemeriksaan"}
            </button>
          </div>
        </header>

        {schedulerMessage ? (
          <div className="mt-5 flex items-center justify-between rounded-xl border border-[#bad8c9] bg-[#edf7f1] px-4 py-3 text-sm text-[#205f47]">
            <span>{schedulerMessage}</span>
            <span className="text-xs font-medium">
              Per {formatDate(effectiveAsOf)}
            </span>
          </div>
        ) : null}
        {scheduler.error ? (
          <ErrorNotice error={scheduler.error} className="mt-5" />
        ) : null}

        <InvoiceStats data={invoices.data} />

        <section className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,1.02fr)_minmax(420px,0.98fr)]">
          <div className="app-card overflow-hidden">
            <div className="grid gap-2 border-b border-[#e4dacd] bg-[#fffaf3] p-3 sm:grid-cols-[1fr_190px]">
              <label className="relative">
                <span className="sr-only">Cari invoice</span>
                <SearchIcon />
                <input
                  className="h-10 w-full rounded-lg border border-[#d9cebf] bg-white pl-10 pr-3 text-sm outline-none placeholder:text-[#9ba09c] focus:border-[#527c6b]"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Cari invoice atau pelanggan"
                  type="search"
                  value={search}
                />
              </label>
              <label>
                <span className="sr-only">Filter status invoice</span>
                <select
                  className="h-10 w-full rounded-lg border border-[#d9cebf] bg-white px-3 text-sm outline-none focus:border-[#527c6b]"
                  onChange={(event) => setStatus(event.target.value)}
                  value={status}
                >
                  <option value="">Semua status</option>
                  <option value="OVERDUE">Terlambat</option>
                  <option value="DUE_SOON">Segera jatuh tempo</option>
                  <option value="OUTSTANDING">Belum dibayar</option>
                  <option value="PAID">Lunas</option>
                </select>
              </label>
            </div>

            <div className="hidden grid-cols-[112px_minmax(130px,1fr)_112px_110px] gap-2 border-b border-[#e4dacd] bg-[#f8f2e9] px-4 py-2.5 text-[11px] text-[#777e79] md:grid">
              <span>Jatuh tempo</span>
              <span>Pelanggan</span>
              <span>Nilai</span>
              <span>Status</span>
            </div>
            {invoices.isPending ? (
              <LoadingBlock label="Memuat invoice…" />
            ) : items.length ? (
              <div className="divide-y divide-[#eadfd2]">
                {items.map((invoice) => (
                  <button
                    className={`grid w-full gap-3 px-4 py-4 text-left transition md:grid-cols-[112px_minmax(130px,1fr)_112px_110px] md:items-center md:gap-2 ${
                      activeInvoiceId === invoice.id
                        ? "bg-[#f5ead9]"
                        : "hover:bg-[#fbf6ee]"
                    }`}
                    key={invoice.id}
                    onClick={() => setSelectedInvoiceId(invoice.id)}
                    type="button"
                  >
                    <div>
                      <p className="text-xs font-medium">{formatDate(invoice.due_date)}</p>
                      <p className="mt-1 text-[11px] text-[#858b86]">
                        {invoice.status === "PAID"
                          ? "Pembayaran selesai"
                          : dueText(invoice.days_until_due)}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">
                        {invoice.customer.name}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-[#747c77]">
                        {invoice.invoice_number}
                      </p>
                    </div>
                    <p className="tabular-nums text-sm font-semibold">
                      {formatMoney(invoice.total)}
                    </p>
                    <InvoiceStatusPill status={invoice.status} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="grid min-h-72 place-items-center p-8 text-center">
                <div>
                  <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-[#f1e7da] text-[#657069]">
                    <InvoiceIcon />
                  </span>
                  <p className="mt-4 text-sm font-semibold">Invoice tidak ditemukan</p>
                  <p className="mt-1.5 text-sm text-[#69716c]">
                    Ubah filter atau jalankan data demo invoice.
                  </p>
                </div>
              </div>
            )}
          </div>

          <aside>
            {detail.isPending && activeInvoiceId ? (
              <div className="app-card">
                <LoadingBlock label="Menyiapkan detail…" />
              </div>
            ) : detail.data ? (
              <InvoicePanel
                invoice={detail.data}
                onRefresh={() => refresh(detail.data.id)}
                token={token!}
              />
            ) : (
              <div className="app-card grid min-h-72 place-items-center p-8 text-center">
                <div>
                  <p className="text-sm font-semibold">Pilih invoice</p>
                  <p className="mt-1.5 text-sm text-[#69716c]">
                    Detail tagihan dan riwayat reminder akan tampil di sini.
                  </p>
                </div>
              </div>
            )}
          </aside>
        </section>
      </main>
    </AppShell>
  );
}

function InvoicePanel({
  invoice,
  token,
  onRefresh,
}: {
  invoice: InvoiceDetail;
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const latest = invoice.reminders[0] ?? null;
  const createDraft = useMutation({
    mutationFn: () => createInvoiceReminder(token, invoice.id),
    onSuccess: onRefresh,
  });

  return (
    <div className="app-card overflow-hidden">
      <div className="bg-[#154938] px-5 py-4 text-white">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate text-base font-semibold">{invoice.customer.name}</p>
            <p className="mt-1 text-xs text-[#bcd2c8]">{invoice.invoice_number}</p>
          </div>
          <InvoiceStatusPill dark status={invoice.status} />
        </div>
        <p className="tabular-nums mt-5 text-3xl font-semibold tracking-[-0.04em]">
          {formatMoney(invoice.total)}
        </p>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#c9dbd4]">
          <span>Terbit {formatDate(invoice.issue_date)}</span>
          <span>Jatuh tempo {formatDate(invoice.due_date)}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 border-b border-[#e4dacd] bg-[#fffaf3]">
        <DetailStat label="Pelanggan" value={invoice.customer.email} />
        <DetailStat
          className="border-l"
          label="Keterlambatan"
          value={
            invoice.status === "PAID"
              ? "Pembayaran selesai"
              : dueText(invoice.days_until_due)
          }
        />
      </div>

      {latest?.status === "PENDING_APPROVAL" ? (
        <ReminderEditor
          key={`${latest.id}-${latest.updated_at}`}
          onRefresh={onRefresh}
          reminder={latest}
          token={token}
        />
      ) : invoice.status === "OVERDUE" && !latest ? (
        <div className="border-b border-[#e4dacd] p-5">
          <p className="text-sm font-semibold">Belum ada pengingat</p>
          <p className="mt-1.5 text-sm leading-6 text-[#69716c]">
            Buat draft dahulu. Pesan tidak akan dikirim sebelum owner
            menyetujuinya.
          </p>
          <button
            className="primary-button mt-4 w-full disabled:opacity-60"
            disabled={createDraft.isPending}
            onClick={() => createDraft.mutate()}
            type="button"
          >
            {createDraft.isPending ? "Membuat draft…" : "Buat draft pengingat"}
          </button>
          {createDraft.error ? (
            <ErrorNotice error={createDraft.error} className="mt-3" />
          ) : null}
        </div>
      ) : latest ? (
        <ReminderOutcome
          onRefresh={onRefresh}
          reminder={latest}
          token={token}
        />
      ) : (
        <div className="border-b border-[#e4dacd] p-5 text-sm text-[#69716c]">
          {invoice.status === "PAID"
            ? "Invoice sudah lunas dan tidak memerlukan pengingat."
            : "Pengingat tersedia setelah invoice melewati tanggal jatuh tempo."}
        </div>
      )}

      <ReminderHistory reminders={invoice.reminders} />
    </div>
  );
}

function ReminderEditor({
  reminder,
  token,
  onRefresh,
}: {
  reminder: InvoiceReminder;
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const [subject, setSubject] = useState(reminder.subject);
  const [body, setBody] = useState(reminder.body);
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => updateInvoiceReminder(token, reminder.id, subject, body),
    onSuccess: async () => {
      setMessage("Perubahan draft tersimpan.");
      await onRefresh();
    },
  });
  const approve = useMutation({
    mutationFn: () => approveInvoiceReminder(token, reminder.id, comment),
    onSuccess: onRefresh,
  });
  const reject = useMutation({
    mutationFn: () => rejectInvoiceReminder(token, reminder.id, comment),
    onSuccess: onRefresh,
  });
  const pending = save.isPending || approve.isPending || reject.isPending;
  const error = save.error || approve.error || reject.error;

  return (
    <div className="border-b border-[#e4dacd] p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">Draft pengingat</p>
          <p className="mt-0.5 text-xs text-[#69716c]">
            {reminder.source === "AI_ASSISTED"
              ? "Copy dibantu AI · angka dikunci dari database"
              : "Template deterministik · fallback aktif"}
          </p>
        </div>
        <span className="rounded-full bg-[#f8f0df] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#805b18]">
          Menunggu approval
        </span>
      </div>

      <label className="mt-4 grid gap-1.5 text-xs font-medium">
        Subjek email
        <input
          className="h-10 rounded-lg border border-[#d9cebf] bg-white px-3 text-sm outline-none focus:border-[#527c6b]"
          maxLength={255}
          onChange={(event) => setSubject(event.target.value)}
          value={subject}
        />
      </label>
      <label className="mt-3 grid gap-1.5 text-xs font-medium">
        Isi pesan
        <textarea
          className="min-h-64 resize-y rounded-lg border border-[#d9cebf] bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-[#527c6b]"
          maxLength={5000}
          onChange={(event) => setBody(event.target.value)}
          value={body}
        />
      </label>
      <button
        className="secondary-button mt-3 w-full disabled:opacity-60"
        disabled={pending || !subject.trim() || !body.trim()}
        onClick={() => save.mutate()}
        type="button"
      >
        {save.isPending ? "Menyimpan…" : "Simpan perubahan"}
      </button>

      <div className="my-5 border-t border-[#e7ddd0]" />
      <label className="grid gap-1.5 text-xs font-medium">
        Catatan keputusan
        <textarea
          className="min-h-20 resize-none rounded-lg border border-[#d9cebf] bg-white px-3 py-2.5 text-sm outline-none focus:border-[#527c6b]"
          onChange={(event) => setComment(event.target.value)}
          placeholder="Alasan persetujuan atau penolakan"
          value={comment}
        />
      </label>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          className="secondary-button disabled:opacity-50"
          disabled={pending || !comment.trim()}
          onClick={() => reject.mutate()}
          type="button"
        >
          {reject.isPending ? "Menolak…" : "Tolak"}
        </button>
        <button
          className="primary-button disabled:opacity-50"
          disabled={pending}
          onClick={() => approve.mutate()}
          type="button"
        >
          {approve.isPending ? "Menyetujui…" : "Setujui & antrekan"}
        </button>
      </div>
      {message ? <p className="mt-3 text-xs text-[#267052]">{message}</p> : null}
      {error ? <ErrorNotice error={error} className="mt-3" /> : null}
    </div>
  );
}

function ReminderOutcome({
  reminder,
  token,
  onRefresh,
}: {
  reminder: InvoiceReminder;
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const retry = useMutation({
    mutationFn: () => retryOutboxMessage(token, reminder.outbox!.id),
    onSuccess: onRefresh,
  });
  const sent = reminder.status === "SENT";
  const failed = reminder.status === "FAILED";
  return (
    <div className="border-b border-[#e4dacd] p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">
            {sent
              ? "Pengingat terkirim"
              : failed
                ? "Pengiriman perlu dicoba ulang"
                : reminder.status === "REJECTED"
                  ? "Draft ditolak"
                  : "Pengingat dalam antrean"}
          </p>
          <p className="mt-1 text-xs text-[#69716c]">
            {reminder.outbox
              ? `${reminder.outbox.recipient_masked} · ${reminder.outbox.attempt_count} percobaan`
              : reminder.decision_comment ?? "Tidak ada pesan eksternal dibuat."}
          </p>
        </div>
        <ReminderStatusPill status={reminder.status} />
      </div>
      {reminder.outbox?.last_error ? (
        <p className="mt-3 rounded-lg bg-[#fff1eb] px-3 py-2 text-xs text-[#983f2f]">
          {reminder.outbox.last_error}
        </p>
      ) : null}
      {failed && reminder.outbox ? (
        <button
          className="secondary-button mt-3 w-full"
          disabled={retry.isPending}
          onClick={() => retry.mutate()}
          type="button"
        >
          {retry.isPending ? "Mengantrekan…" : "Coba kirim ulang"}
        </button>
      ) : null}
      {sent ? (
        <a
          className="secondary-button mt-3 flex w-full justify-center"
          href="http://localhost:8025"
          rel="noreferrer"
          target="_blank"
        >
          Buka Mailpit
        </a>
      ) : null}
    </div>
  );
}

function ReminderHistory({ reminders }: { reminders: InvoiceReminder[] }) {
  return (
    <div className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Riwayat reminder</p>
        <span className="text-xs text-[#777e79]">{reminders.length} aktivitas</span>
      </div>
      {reminders.length ? (
        <div className="mt-4 space-y-4">
          {reminders.map((reminder, index) => (
            <div className="relative grid grid-cols-[14px_1fr] gap-3" key={reminder.id}>
              {index < reminders.length - 1 ? (
                <span className="absolute bottom-[-18px] left-[6px] top-3 w-px bg-[#ded5ca]" />
              ) : null}
              <span className="z-10 mt-1 h-3.5 w-3.5 rounded-full border-[3px] border-[#fdfaf5] bg-[#d56f3a] ring-1 ring-[#e4c4ae]" />
              <div>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold">Reminder #{reminder.sequence}</p>
                  <ReminderStatusPill status={reminder.status} />
                </div>
                <p className="mt-1 text-xs text-[#777e79]">
                  {formatDateTime(reminder.created_at)} ·{" "}
                  {reminder.source === "AI_ASSISTED" ? "AI-assisted" : "Fallback"}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-[#777e79]">Belum ada reminder.</p>
      )}
    </div>
  );
}

function InvoiceStats({ data }: { data: Awaited<ReturnType<typeof getInvoices>> | undefined }) {
  const counts = data?.counts;
  return (
    <section className="app-card mt-6 grid overflow-hidden sm:grid-cols-2 xl:grid-cols-5">
      <Stat label="Piutang terbuka" value={formatMoney(counts?.outstanding_amount ?? "0")} />
      <Stat className="border-t sm:border-l sm:border-t-0" label="Terlambat" value={counts?.overdue ?? 0} />
      <Stat className="border-t xl:border-l xl:border-t-0" label="Jatuh tempo dekat" value={counts?.due_soon ?? 0} />
      <Stat className="border-t sm:border-l xl:border-t-0" label="Belum dibayar" value={counts?.outstanding ?? 0} />
      <Stat className="border-t xl:border-l xl:border-t-0" label="Lunas" value={counts?.paid ?? 0} />
    </section>
  );
}

function Stat({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string | number;
  className?: string;
}) {
  return (
    <div className={`border-[#e4dacd] px-5 py-4 ${className}`}>
      <p className="text-xs text-[#69716c]">{label}</p>
      <p className="tabular-nums mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function DetailStat({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={`min-w-0 border-[#e4dacd] px-5 py-3.5 ${className}`}>
      <p className="text-[11px] text-[#777e79]">{label}</p>
      <p className="mt-1 truncate text-xs font-semibold">{value}</p>
    </div>
  );
}

function InvoiceStatusPill({
  status,
  dark = false,
}: {
  status: InvoiceStatus;
  dark?: boolean;
}) {
  const style = dark
    ? "bg-white/12 text-white"
    : status === "OVERDUE"
      ? "bg-[#fae8de] text-[#9d472d]"
      : status === "DUE_SOON"
        ? "bg-[#f8f0df] text-[#805b18]"
        : status === "PAID"
          ? "bg-[#e3f2e9] text-[#176846]"
          : "bg-[#edf0ec] text-[#5d6660]";
  return (
    <span className={`w-fit rounded-full px-2.5 py-1 text-[10px] font-semibold ${style}`}>
      {statusLabels[status]}
    </span>
  );
}

function ReminderStatusPill({ status }: { status: InvoiceReminder["status"] }) {
  const labels: Record<InvoiceReminder["status"], string> = {
    PENDING_APPROVAL: "Menunggu",
    APPROVED: "Disetujui",
    REJECTED: "Ditolak",
    QUEUED: "Antrean",
    SENT: "Terkirim",
    FAILED: "Gagal",
  };
  const style =
    status === "SENT"
      ? "bg-[#e3f2e9] text-[#176846]"
      : status === "FAILED" || status === "REJECTED"
        ? "bg-[#fae8de] text-[#9d472d]"
        : "bg-[#f8f0df] text-[#805b18]";
  return (
    <span className={`w-fit rounded-full px-2 py-1 text-[10px] font-semibold ${style}`}>
      {labels[status]}
    </span>
  );
}

function ErrorNotice({ error, className = "" }: { error: Error; className?: string }) {
  const message = error instanceof ApiError ? error.message : "Terjadi kesalahan. Coba lagi.";
  return (
    <p className={`rounded-lg border border-[#edc0ae] bg-[#fff2ec] px-3 py-2 text-xs text-[#963d32] ${className}`}>
      {message}
    </p>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="grid min-h-64 place-items-center" role="status">
      <div className="text-center">
        <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#d7dad5] border-t-[#174d3a]" />
        <p className="mt-3 text-sm text-[#69716c]">{label}</p>
      </div>
    </div>
  );
}

function dueText(days: number): string {
  if (days < 0) return `${Math.abs(days)} hari terlambat`;
  if (days === 0) return "Jatuh tempo hari ini";
  return `${days} hari lagi`;
}

function formatMoney(value: string): string {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" className="absolute left-3 top-3 text-[#8c948e]" fill="none" height="16" viewBox="0 0 24 24" width="16">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.7" />
      <path d="m16 16 4 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

function InvoiceIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="20" viewBox="0 0 24 24" width="20">
      <path d="M6 3h9l3 3v15l-3-1.5L12 21l-3-1.5L6 21V3Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M9 9h6M9 13h6M9 17h3" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}
