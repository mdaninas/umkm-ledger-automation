"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Banknote,
  BookCheck,
  CircleAlert,
  FileClock,
  FileStack,
  Landmark,
  Upload,
  WalletCards,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { AppShell, useSessionToken } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getDashboardSummary, getHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  const cash = Number(summary.data?.cash_balance ?? 0);
  const bank = Number(summary.data?.bank_balance ?? 0);
  const comparisonBase = Math.max(income, expenses, 1);
  const net = income - expenses;
  const healthy = health.data?.status === "healthy";

  const balances = [
    {
      label: "Kas",
      description: "Saldo akun kas",
      value: cash,
      icon: WalletCards,
    },
    {
      label: "Bank",
      description: "Saldo rekening tercatat",
      value: bank,
      icon: Landmark,
    },
    {
      label: "Pendapatan",
      description: "Jurnal pendapatan final",
      value: income,
      icon: Banknote,
    },
    {
      label: "Beban",
      description: "Jurnal beban final",
      value: expenses,
      icon: FileStack,
    },
  ];

  const activities = [
    {
      label: "Dokumen perlu ditinjau",
      description: "Menunggu koreksi atau konfirmasi owner",
      value: summary.data?.needs_review_count,
      icon: CircleAlert,
      tone: "warning" as const,
    },
    {
      label: "Draft jurnal",
      description: "Sudah disiapkan tetapi belum final",
      value: summary.data?.draft_journal_count,
      icon: FileClock,
      tone: "neutral" as const,
    },
    {
      label: "Jurnal terposting",
      description: "Seimbang dan sudah masuk pembukuan",
      value: summary.data?.posted_journal_count,
      icon: BookCheck,
      tone: "success" as const,
    },
  ];

  return (
    <AppShell>
      <main className="mx-auto max-w-[1280px] px-5 py-7 sm:px-8 sm:py-9 xl:px-10 xl:py-10">
        <header className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <p className="eyebrow">Workspace keuangan</p>
              <Badge
                className={cn(
                  "gap-1.5 border-0 px-2 text-[10px]",
                  healthy
                    ? "bg-[#e3efe8] text-[#246449]"
                    : "bg-[#f8eadf] text-[#8b4c2d]",
                )}
                variant="secondary"
              >
                <span className="size-1.5 rounded-full bg-current" />
                {health.isPending
                  ? "Memeriksa"
                  : healthy
                    ? "Tersinkron"
                    : "Terbatas"}
              </Badge>
            </div>
            <h1 className="text-[30px] font-semibold tracking-[-0.045em] sm:text-[34px]">
              Ringkasan keuangan
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              Posisi terbaru berdasarkan dokumen yang sudah ditinjau dan jurnal
              yang telah diposting.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild className="h-10 px-4" size="lg" variant="outline">
              <Link href="/approvals">Buka approval</Link>
            </Button>
            <Button asChild className="h-10 px-4" size="lg">
              <Link href="/inbox">
                <Upload data-icon="inline-start" />
                Unggah dokumen
              </Link>
            </Button>
          </div>
        </header>

        <section className="mt-8 grid gap-3 min-[380px]:grid-cols-2 sm:gap-4 xl:grid-cols-4">
          {balances.map((item) => (
            <BalanceCard
              description={item.description}
              icon={item.icon}
              key={item.label}
              label={item.label}
              loading={summary.isPending}
              value={item.value}
            />
          ))}
        </section>

        <section className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(290px,0.55fr)]">
          <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
            <CardHeader className="border-b px-5 py-5 sm:px-6">
              <CardTitle>Pendapatan dan beban</CardTitle>
              <CardDescription>
                Perbandingan seluruh jurnal final
              </CardDescription>
              <CardAction>
                <Badge
                  className={cn(
                    "h-6 px-2.5 tabular-nums",
                    net >= 0
                      ? "bg-[#e3efe8] text-[#246449]"
                      : "bg-[#f8e7e2] text-[#963d32]",
                  )}
                  variant="secondary"
                >
                  Neto {summary.data ? rupiah.format(net) : "—"}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent className="px-5 py-6 sm:px-6 sm:py-7">
              <div className="space-y-7">
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
              <p className="mt-7 border-t pt-4 text-xs leading-5 text-muted-foreground">
                Hanya transaksi yang sudah ditinjau dan diposting yang dihitung.
              </p>
            </CardContent>
          </Card>

          <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
            <CardHeader className="border-b px-5 py-5">
              <span className="mb-2 grid size-9 place-items-center rounded-lg bg-[#f7e4d8] text-[#b8562b]">
                <CircleAlert className="size-[18px]" />
              </span>
              <CardTitle>Perlu perhatian</CardTitle>
              <CardDescription>
                Dokumen yang membutuhkan keputusan
              </CardDescription>
            </CardHeader>
            <CardContent className="px-5 py-5">
              <p className="tabular-nums text-4xl font-semibold tracking-[-0.05em]">
                {summary.data?.needs_review_count ?? "—"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                dokumen menunggu peninjauan
              </p>
              <Button
                asChild
                className="mt-5 w-full justify-between"
                variant="outline"
              >
                <Link href="/inbox?status=NEEDS_REVIEW">
                  Tinjau dokumen
                  <ArrowRight data-icon="inline-end" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        </section>

        <Card className="mt-5 gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
          <CardHeader className="border-b px-5 py-5 sm:px-6">
            <CardTitle>Aktivitas pembukuan</CardTitle>
            <CardDescription>
              Status dokumen dan jurnal saat ini
            </CardDescription>
            <CardAction>
              <Button asChild size="sm" variant="ghost">
                <Link href="/inbox">
                  Lihat semua
                  <ArrowRight data-icon="inline-end" />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="divide-y px-0">
            {activities.map((activity) => (
              <ActivityRow
                description={activity.description}
                icon={activity.icon}
                key={activity.label}
                label={activity.label}
                tone={activity.tone}
                value={activity.value ?? "—"}
              />
            ))}
          </CardContent>
        </Card>
      </main>
    </AppShell>
  );
}

function BalanceCard({
  label,
  description,
  value,
  icon: Icon,
  loading,
}: {
  label: string;
  description: string;
  value: number;
  icon: LucideIcon;
  loading: boolean;
}) {
  const negative = value < 0;

  return (
    <Card className="gap-0 py-0 shadow-[0_8px_24px_rgb(17_36_28/0.03)] ring-border">
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <p
              className={cn(
                "tabular-nums mt-2 truncate text-[19px] font-semibold tracking-[-0.035em] sm:text-[22px]",
                negative && "text-[#a34236]",
              )}
            >
              {loading ? "—" : rupiah.format(value)}
            </p>
          </div>
          <span className="hidden size-9 shrink-0 place-items-center rounded-lg bg-accent text-primary sm:grid">
            <Icon className="size-4 sm:size-[18px]" strokeWidth={1.8} />
          </span>
        </div>
        <p className="mt-4 text-[11px] text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
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
      <div className="mb-2.5 flex items-center justify-between gap-4 text-sm">
        <span className="font-medium text-muted-foreground">{label}</span>
        <span className="tabular-nums font-semibold">{rupiah.format(value)}</span>
      </div>
      <Progress
        aria-label={`${label}: ${rupiah.format(value)}`}
        className={cn(
          "h-2 bg-muted",
          tone === "expense" && "[&_[data-slot=progress-indicator]]:bg-[#d8753f]",
        )}
        value={width}
      />
    </div>
  );
}

function ActivityRow({
  label,
  description,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  description: string;
  value: string | number;
  icon: LucideIcon;
  tone: "warning" | "neutral" | "success";
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-4 sm:px-6">
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg",
          tone === "warning" && "bg-[#f8e8df] text-[#b8562b]",
          tone === "neutral" && "bg-muted text-muted-foreground",
          tone === "success" && "bg-[#e3efe8] text-[#246449]",
        )}
      >
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {description}
        </p>
      </div>
      <p className="tabular-nums text-lg font-semibold">{value}</p>
    </div>
  );
}
