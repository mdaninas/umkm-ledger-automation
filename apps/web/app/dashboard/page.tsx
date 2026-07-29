"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AppShell, useSessionToken } from "@/components/app-shell";
import { getDashboardSummary, getHealth } from "@/lib/api";

const rupiah = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

export default function DashboardPage() {
  const token = useSessionToken();
  const summary = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => getDashboardSummary(token!),
    enabled: Boolean(token),
  });
  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: getHealth,
    refetchInterval: 30_000,
  });

  const income = Number(summary.data?.posted_income ?? 0);
  const expenses = Number(summary.data?.posted_expenses ?? 0);
  const comparisonBase = Math.max(income, expenses, 1);
  const net = income - expenses;
  const healthy = health.data?.status === "healthy";

  const balances = [
    {
      label: "Kas",
      value: summary.data ? rupiah.format(Number(summary.data.cash_balance)) : "—",
    },
    {
      label: "Bank",
      value: summary.data ? rupiah.format(Number(summary.data.bank_balance)) : "—",
    },
    {
      label: "Pendapatan tercatat",
      value: summary.data ? rupiah.format(income) : "—",
    },
    {
      label: "Beban tercatat",
      value: summary.data ? rupiah.format(expenses) : "—",
    },
  ];

  return (
    <AppShell>
      <main className="mx-auto max-w-[1240px] px-5 py-7 sm:px-8 sm:py-9 xl:px-10">
        <header className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
          <div>
            <p className="eyebrow text-[#8a6a51]">Workspace keuangan</p>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] sm:text-[28px]">
              Ringkasan
            </h1>
            <p className="mt-1.5 text-sm text-[#69716c]">
              Posisi keuangan berdasarkan jurnal yang sudah diposting.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link className="secondary-button" href="/approvals">
              Buka approval
            </Link>
            <Link className="primary-button" href="/inbox">
              <UploadIcon />
              Unggah dokumen
            </Link>
          </div>
        </header>

        <section className="relative mt-7 overflow-hidden rounded-2xl border border-[#31584a] bg-[#173f32] text-[#fffaf0] shadow-[0_14px_30px_rgb(31_55_45/0.12)]">
          <span
            aria-hidden="true"
            className="absolute -right-16 -top-24 h-64 w-64 rounded-full bg-[#d56f3a] opacity-90"
          />
          <span
            aria-hidden="true"
            className="absolute -right-2 top-9 h-48 w-48 rounded-full border-[34px] border-[#f0c58f] opacity-20"
          />
          <div className="relative flex items-center justify-between border-b border-[#426659] px-5 py-4 sm:px-6">
            <div>
              <h2 className="text-sm font-semibold">Posisi keuangan</h2>
              <p className="mt-0.5 text-xs text-[#afc3ba]">Nilai jurnal final</p>
            </div>
            <div className="flex items-center gap-2 rounded-full bg-[#0f3027]/60 px-3 py-1.5 text-xs text-[#d9e5df]">
              <span
                className={`status-dot ${
                  healthy ? "text-[#df9a60]" : "text-[#f0c58f]"
                }`}
              />
              {health.isPending
                ? "Memeriksa sistem"
                : healthy
                  ? "Data sinkron"
                  : "Sistem terbatas"}
            </div>
          </div>
          <div className="relative grid sm:grid-cols-2 xl:grid-cols-4">
            {balances.map((item, index) => (
              <div
                className={`px-5 py-5 sm:px-6 ${
                  index > 0 ? "border-t border-[#426659] sm:border-l" : ""
                } ${index === 2 ? "sm:border-t xl:border-t-0" : ""}`}
                key={item.label}
              >
                <p className="text-xs text-[#afc3ba]">{item.label}</p>
                <p className="tabular-nums mt-2 truncate text-xl font-semibold tracking-[-0.025em] text-white">
                  {item.value}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.55fr)]">
          <article className="app-card p-5 sm:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold">Pendapatan dan beban</h2>
                <p className="mt-1 text-xs text-[#777e79]">
                  Perbandingan seluruh jurnal final
                </p>
              </div>
              <span
                className={`rounded-md px-2 py-1 text-xs font-medium ${
                  net >= 0
                    ? "bg-[#e5f0e9] text-[#176846]"
                    : "bg-[#f7e3da] text-[#963d32]"
                }`}
              >
                Neto {summary.data ? rupiah.format(net) : "—"}
              </span>
            </div>

            <div className="mt-8 space-y-6">
              <ComparisonBar
                label="Pendapatan"
                value={income}
                width={(income / comparisonBase) * 100}
              />
              <ComparisonBar
                label="Beban"
                tone="expense"
                value={expenses}
                width={(expenses / comparisonBase) * 100}
              />
            </div>

            <div className="mt-8 border-t border-[#e4dacd] pt-4 text-xs leading-5 text-[#69716c]">
              Hanya transaksi yang sudah ditinjau dan diposting yang dihitung.
            </div>
          </article>

          <aside className="overflow-hidden rounded-[14px] border border-[#e2bfaa] bg-[#f7e3d5] shadow-[0_1px_2px_rgb(56_43_29/0.035)]">
            <div className="flex items-center justify-between border-b border-[#e6c6b3] px-5 py-4">
              <h2 className="text-sm font-semibold text-[#6f321d]">Perlu perhatian</h2>
              <span className="grid h-8 w-8 place-items-center rounded-full bg-[#d56f3a] text-sm text-white">
                !
              </span>
            </div>
            <div className="px-5 py-5">
              <p className="tabular-nums text-4xl font-semibold tracking-[-0.04em] text-[#5b2d1d]">
                {summary.data?.needs_review_count ?? "—"}
              </p>
              <p className="mt-1 text-sm text-[#86543d]">
                dokumen menunggu peninjauan
              </p>
              <Link
                className="mt-5 flex items-center justify-between border-t border-[#e0bba6] pt-4 text-sm font-semibold text-[#74361f]"
                href="/inbox?status=NEEDS_REVIEW"
              >
                Tinjau dokumen
                <span aria-hidden="true">→</span>
              </Link>
            </div>
          </aside>
        </section>

        <section className="app-card mt-5 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[#e4dacd] px-5 py-4 sm:px-6">
            <div>
              <h2 className="text-sm font-semibold">Aktivitas pembukuan</h2>
              <p className="mt-0.5 text-xs text-[#777e79]">
                Status dokumen dan jurnal saat ini
              </p>
            </div>
            <Link className="text-xs font-medium text-[#174d3a]" href="/inbox">
              Lihat semua
            </Link>
          </div>
          <div className="divide-y divide-[#e4dacd]">
            <ActivityRow
              description="Menunggu koreksi atau konfirmasi owner"
              label="Dokumen perlu ditinjau"
              value={summary.data?.needs_review_count ?? "—"}
            />
            <ActivityRow
              description="Jurnal sudah disiapkan tetapi belum final"
              label="Draft jurnal"
              value={summary.data?.draft_journal_count ?? "—"}
            />
            <ActivityRow
              description="Jurnal seimbang dan sudah tercatat"
              label="Jurnal terposting"
              value={summary.data?.posted_journal_count ?? "—"}
            />
          </div>
        </section>
      </main>
    </AppShell>
  );
}

function ComparisonBar({
  label,
  value,
  width,
  tone = "income",
}: {
  label: string;
  value: number;
  width: number;
  tone?: "income" | "expense";
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-4 text-sm">
        <span className="text-[#5f6762]">{label}</span>
        <span className="tabular-nums font-medium">{rupiah.format(value)}</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-[#eee7dc]">
        <div
          className={`h-full rounded-full ${
            tone === "income" ? "bg-[#2c7356]" : "bg-[#d56f3a]"
          }`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function ActivityRow({
  label,
  description,
  value,
}: {
  label: string;
  description: string;
  value: string | number;
}) {
  return (
    <div className="grid gap-2 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-6">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-0.5 text-xs text-[#777e79]">{description}</p>
      </div>
      <p className="tabular-nums text-lg font-semibold">{value}</p>
    </div>
  );
}

function UploadIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 24 24" width="16">
      <path d="M12 16V4m0 0L7 9m5-5 5 5M5 15v5h14v-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}
