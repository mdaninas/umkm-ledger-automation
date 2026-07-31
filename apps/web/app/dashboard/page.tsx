"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CalendarRange,
  Download,
  FileCheck2,
  Landmark,
  LoaderCircle,
  ReceiptText,
  RefreshCw,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";
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
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import {
  type DashboardReport,
  downloadReportCsv,
  getDashboardReport,
  getWeeklyDigests,
  runWeeklyDigest,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const rupiah = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

const compactRupiah = new Intl.NumberFormat("id-ID", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const dateLabel = new Intl.DateTimeFormat("id-ID", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const shortDateLabel = new Intl.DateTimeFormat("id-ID", {
  day: "numeric",
  month: "short",
});

const chartConfig = {
  closing_balance: {
    label: "Saldo tersedia",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig;

type RangeOption = {
  value: string;
  label: string;
  startDate: string;
  endDate: string;
};

export default function DashboardPage() {
  const token = useSessionToken();
  const queryClient = useQueryClient();
  const ranges = useMemo(() => buildRanges(), []);
  const [rangeKey, setRangeKey] = useState("month");
  const initialRange = ranges[0];
  const [startDate, setStartDate] = useState(initialRange.startDate);
  const [endDate, setEndDate] = useState(initialRange.endDate);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const report = useQuery({
    queryKey: ["dashboard-report", startDate, endDate],
    queryFn: () => getDashboardReport(token!, startDate, endDate),
    enabled: Boolean(token),
  });
  const digests = useQuery({
    queryKey: ["weekly-digests"],
    queryFn: () => getWeeklyDigests(token!),
    enabled: Boolean(token),
  });
  const digestMutation = useMutation({
    mutationFn: () => runWeeklyDigest(token!, endDate),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["weekly-digests"] }),
  });

  function selectRange(value: string) {
    setRangeKey(value);
    const selected = ranges.find((range) => range.value === value);
    if (selected) {
      setStartDate(selected.startDate);
      setEndDate(selected.endDate);
    }
  }

  async function exportCsv() {
    if (!token) return;
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await downloadReportCsv(
        token,
        startDate,
        endDate,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(
        error instanceof Error ? error.message : "Laporan gagal diunduh.",
      );
    } finally {
      setExporting(false);
    }
  }

  return (
    <AppShell>
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7 sm:py-8 xl:px-10 xl:py-9">
        <header className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="eyebrow mb-3">Laporan keuangan</p>
            <h1 className="text-[30px] font-semibold tracking-[-0.045em] sm:text-[36px]">
              Ruang kendali
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Baca posisi kas, pekerjaan otomatis, dan hal yang perlu ditindak
              dari satu sumber pembukuan.
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="relative">
              <span className="sr-only">Pilih periode laporan</span>
              <CalendarRange className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <select
                className="h-10 min-w-48 appearance-none rounded-lg border bg-card py-0 pl-9 pr-8 text-sm font-medium shadow-xs outline-none focus:border-ring focus:ring-3 focus:ring-ring/20"
                onChange={(event) => selectRange(event.target.value)}
                value={rangeKey}
              >
                {ranges.map((range) => (
                  <option key={range.value} value={range.value}>
                    {range.label}
                  </option>
                ))}
                {rangeKey === "custom" && (
                  <option value="custom">Periode pilihan</option>
                )}
              </select>
            </label>
            <div className="hidden items-center gap-1.5 rounded-lg border bg-card p-1 shadow-xs lg:flex">
              <input
                aria-label="Tanggal mulai"
                className="h-8 rounded-md bg-transparent px-2 text-xs outline-none focus:bg-muted"
                max={endDate}
                onChange={(event) => {
                  setRangeKey("custom");
                  setStartDate(event.target.value);
                }}
                type="date"
                value={startDate}
              />
              <span className="text-xs text-muted-foreground">sampai</span>
              <input
                aria-label="Tanggal akhir"
                className="h-8 rounded-md bg-transparent px-2 text-xs outline-none focus:bg-muted"
                min={startDate}
                onChange={(event) => {
                  setRangeKey("custom");
                  setEndDate(event.target.value);
                }}
                type="date"
                value={endDate}
              />
            </div>
            <Button
              className="h-10 px-3"
              disabled={exporting || report.isPending}
              onClick={exportCsv}
              variant="outline"
            >
              {exporting ? (
                <LoaderCircle className="animate-spin" data-icon="inline-start" />
              ) : (
                <Download data-icon="inline-start" />
              )}
              Ekspor CSV
            </Button>
          </div>
        </header>

        {exportError && (
          <p className="mt-3 text-right text-xs text-destructive" role="alert">
            {exportError}
          </p>
        )}

        {report.isPending ? (
          <DashboardLoading />
        ) : report.isError || !report.data ? (
          <DashboardError
            message={
              report.error instanceof Error
                ? report.error.message
                : "Laporan belum dapat dimuat."
            }
            retry={() => report.refetch()}
          />
        ) : (
          <DashboardContent
            digest={digests.data?.[0]}
            digestError={digestMutation.error}
            digestPending={digestMutation.isPending}
            generateDigest={() => digestMutation.mutate()}
            report={report.data}
          />
        )}
      </main>
    </AppShell>
  );
}

function DashboardContent({
  report,
  digest,
  digestPending,
  digestError,
  generateDigest,
}: {
  report: DashboardReport;
  digest?: {
    period_start: string;
    period_end: string;
    narrative: string;
    source_refs: Array<Record<string, unknown>>;
  };
  digestPending: boolean;
  digestError: Error | null;
  generateDigest: () => void;
}) {
  const overview = report.overview;
  const chartData = report.cashflow.map((point) => ({
    ...point,
    closing_balance: Number(point.closing_balance),
  }));
  const maxExpense = Math.max(
    ...report.expense_breakdown.map((item) => Number(item.amount)),
    1,
  );

  return (
    <>
      <section className="mt-7 grid gap-3 md:grid-cols-3">
        <MetricCard
          change={overview.income_change_percent}
          description="Pendapatan yang sudah diposting"
          label="Pendapatan"
          value={overview.income}
        />
        <MetricCard
          change={overview.expense_change_percent}
          description="Beban yang sudah diposting"
          inverseChange
          label="Beban"
          value={overview.expenses}
        />
        <MetricCard
          description="Saldo kas dan bank hingga akhir periode"
          featured
          label="Kas tersedia"
          value={overview.available_cash}
        />
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,0.65fr)]">
        <Card className="gap-0 overflow-hidden py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
          <CardHeader className="border-b px-5 py-5 sm:px-6">
            <CardTitle>Gerak kas</CardTitle>
            <CardDescription>
              Saldo penutupan harian dari akun kas dan bank
            </CardDescription>
            <CardAction>
              <p className="text-right text-xs text-muted-foreground">
                {formatPeriod(report.period.start_date, report.period.end_date)}
              </p>
            </CardAction>
          </CardHeader>
          <CardContent className="px-2 pb-5 pt-4 sm:px-5 sm:pt-5">
            <ChartContainer
              className="h-[270px] w-full sm:h-[310px]"
              config={chartConfig}
              initialDimension={{ width: 760, height: 310 }}
            >
              <LineChart
                accessibilityLayer
                data={chartData}
                margin={{ left: 0, right: 12, top: 10 }}
              >
                <CartesianGrid strokeDasharray="3 5" vertical={false} />
                <XAxis
                  axisLine={false}
                  dataKey="date"
                  interval="preserveStartEnd"
                  minTickGap={28}
                  tickFormatter={(value) => formatShortDate(String(value))}
                  tickLine={false}
                  tickMargin={10}
                />
                <YAxis
                  axisLine={false}
                  tickFormatter={(value) => compactRupiah.format(Number(value))}
                  tickLine={false}
                  tickMargin={8}
                  width={54}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      formatter={(value) => (
                        <div className="flex min-w-40 items-center justify-between gap-4">
                          <span className="text-muted-foreground">
                            Saldo tersedia
                          </span>
                          <span className="tabular-nums font-semibold text-foreground">
                            {rupiah.format(Number(value))}
                          </span>
                        </div>
                      )}
                      hideIndicator
                      labelFormatter={(value) =>
                        formatFullDate(String(value))
                      }
                    />
                  }
                />
                <Line
                  activeDot={false}
                  dataKey="closing_balance"
                  dot={false}
                  stroke="var(--color-closing_balance)"
                  strokeLinecap="round"
                  strokeWidth={2.5}
                  type="monotone"
                />
              </LineChart>
            </ChartContainer>
            <div className="mx-3 mt-1 flex flex-wrap gap-x-5 gap-y-2 border-t pt-4 text-xs text-muted-foreground sm:mx-1">
              <span>
                Arus masuk {rupiah.format(sum(report.cashflow, "inflow"))}
              </span>
              <span>
                Arus keluar {rupiah.format(sum(report.cashflow, "outflow"))}
              </span>
              <span className="font-medium text-foreground">
                Neto {rupiah.format(Number(overview.net_cash_flow))}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card className="gap-0 overflow-hidden py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
          <CardHeader className="border-b px-5 py-5">
            <CardTitle>Antrean tindakan</CardTitle>
            <CardDescription>
              {report.alerts.length} hal perlu diperiksa
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {report.alerts.length ? (
              <div className="divide-y">
                {report.alerts.slice(0, 5).map((alert) => (
                  <Link
                    className="group block px-5 py-4 transition-colors hover:bg-muted/55"
                    href={alert.source_url}
                    key={alert.id}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <Badge
                        className={severityClass(alert.severity)}
                        variant="secondary"
                      >
                        {severityLabel(alert.severity)}
                      </Badge>
                      <ArrowUpRight className="size-4 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                    </div>
                    <p className="mt-2.5 text-sm font-semibold leading-5">
                      {alert.title}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                      {alert.description}
                    </p>
                    <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
                      Aturan: {alert.rule}
                    </p>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="px-5 py-10 text-center">
                <FileCheck2 className="mx-auto size-6 text-primary" />
                <p className="mt-3 text-sm font-semibold">Tidak ada alert aktif</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Tidak ada pengecualian yang melewati aturan saat ini.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-[1fr_1.08fr_1.18fr]">
        <AutomationCard report={report} />
        <ExpenseCard maxExpense={maxExpense} report={report} />
        <InvoiceCard report={report} />
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
          <CardHeader className="border-b px-5 py-5 sm:px-6">
            <CardTitle>Ringkasan mingguan</CardTitle>
            <CardDescription>
              Narasi dihitung dari metrik yang dapat ditelusuri
            </CardDescription>
            <CardAction>
              <Button
                disabled={digestPending}
                onClick={generateDigest}
                size="sm"
                variant="outline"
              >
                {digestPending ? (
                  <LoaderCircle className="animate-spin" data-icon="inline-start" />
                ) : (
                  <RefreshCw data-icon="inline-start" />
                )}
                {digest ? "Perbarui" : "Buat ringkasan"}
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="px-5 py-5 sm:px-6">
            {digest ? (
              <>
                <p className="text-sm leading-7 text-foreground/90">
                  {digest.narrative}
                </p>
                <p className="mt-4 border-t pt-3 text-[11px] text-muted-foreground">
                  {formatPeriod(digest.period_start, digest.period_end)} · {" "}
                  {digest.source_refs.length} referensi sumber
                </p>
              </>
            ) : (
              <p className="text-sm leading-6 text-muted-foreground">
                Buat ringkasan untuk melihat perubahan kas, beban, alert, dan
                otomatisasi selama tujuh hari terakhir.
              </p>
            )}
            {digestError && (
              <p className="mt-3 text-xs text-destructive" role="alert">
                {digestError.message}
              </p>
            )}
          </CardContent>
        </Card>

        <EvidenceCard report={report} />
      </section>
    </>
  );
}

function MetricCard({
  label,
  description,
  value,
  change,
  inverseChange = false,
  featured = false,
}: {
  label: string;
  description: string;
  value: string;
  change?: string | null;
  inverseChange?: boolean;
  featured?: boolean;
}) {
  const numericChange = change === null || change === undefined ? null : Number(change);
  const favorable = numericChange === null ? null : inverseChange ? numericChange <= 0 : numericChange >= 0;

  return (
    <Card
      className={cn(
        "gap-0 py-0 shadow-[0_8px_24px_rgb(17_36_28/0.03)] ring-border",
        featured && "bg-[#143f32] text-white ring-[#143f32]",
      )}
    >
      <CardContent className="p-5 sm:p-6">
        <p
          className={cn(
            "text-xs font-medium",
            featured ? "text-white/65" : "text-muted-foreground",
          )}
        >
          {label}
        </p>
        <p className="tabular-nums mt-3 text-[27px] font-semibold tracking-[-0.05em] sm:text-[30px]">
          {rupiah.format(Number(value))}
        </p>
        <div className="mt-4 flex min-h-5 items-center justify-between gap-3">
          <p
            className={cn(
              "text-[11px] leading-4",
              featured ? "text-white/60" : "text-muted-foreground",
            )}
          >
            {description}
          </p>
          {numericChange !== null && (
            <span
              className={cn(
                "flex shrink-0 items-center gap-1 text-[11px] font-semibold tabular-nums",
                favorable ? "text-[#277456]" : "text-[#ad4f32]",
                featured && "text-white/80",
              )}
            >
              {numericChange >= 0 ? (
                <ArrowUpRight className="size-3" />
              ) : (
                <ArrowDownRight className="size-3" />
              )}
              {Math.abs(numericChange).toLocaleString("id-ID", {
                maximumFractionDigits: 1,
              })}
              %
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function AutomationCard({ report }: { report: DashboardReport }) {
  const automation = report.automation;
  const rate = Number(automation.automation_rate_percent);

  return (
    <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
      <CardHeader className="border-b px-5 py-5">
        <CardTitle>Mesin otomatisasi</CardTitle>
        <CardDescription>Hasil workflow dalam periode ini</CardDescription>
        <CardAction>
          <Bot className="size-4 text-muted-foreground" />
        </CardAction>
      </CardHeader>
      <CardContent className="px-5 py-5">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="tabular-nums text-4xl font-semibold tracking-[-0.06em]">
              {rate.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              selesai tanpa intervensi
            </p>
          </div>
          <p className="text-right text-xs leading-5 text-muted-foreground">
            {automation.succeeded} dari {automation.total_workflows} workflow
          </p>
        </div>
        <Progress className="mt-5 h-2" value={rate} />
        <dl className="mt-5 grid grid-cols-3 divide-x border-t pt-4 text-center">
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Gagal
            </dt>
            <dd className="tabular-nums mt-1 text-lg font-semibold">
              {automation.failed}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Retry
            </dt>
            <dd className="tabular-nums mt-1 text-lg font-semibold">
              {automation.retry_count}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Review
            </dt>
            <dd className="tabular-nums mt-1 text-lg font-semibold">
              {automation.waiting_review}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

function ExpenseCard({
  report,
  maxExpense,
}: {
  report: DashboardReport;
  maxExpense: number;
}) {
  return (
    <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
      <CardHeader className="border-b px-5 py-5">
        <CardTitle>Komposisi beban</CardTitle>
        <CardDescription>Kategori terbesar periode ini</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 px-5 py-5">
        {report.expense_breakdown.slice(0, 5).map((item) => (
          <div className="scroll-mt-24" id={`expense-${item.account_code}`} key={item.account_code}>
            <div className="mb-2 flex items-center justify-between gap-4 text-xs">
              <span className="truncate font-medium">{item.account_name}</span>
              <span className="tabular-nums text-muted-foreground">
                {compactRupiah.format(Number(item.amount))}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-[#4e7b68]"
                style={{ width: `${(Number(item.amount) / maxExpense) * 100}%` }}
              />
            </div>
          </div>
        ))}
        {!report.expense_breakdown.length && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Belum ada beban yang diposting.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function InvoiceCard({ report }: { report: DashboardReport }) {
  return (
    <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border lg:col-span-2 xl:col-span-1">
      <CardHeader className="border-b px-5 py-5">
        <CardTitle>Piutang terdekat</CardTitle>
        <CardDescription>Tagihan yang masih perlu ditagih</CardDescription>
        <CardAction>
          <Button asChild size="sm" variant="ghost">
            <Link href="/invoices">
              Semua
              <ArrowRight data-icon="inline-end" />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {report.outstanding_invoices.length ? (
          <div className="divide-y">
            {report.outstanding_invoices.slice(0, 4).map((invoice) => (
              <Link
                className="group flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-muted/55"
                href={invoice.source_url}
                key={invoice.id}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">
                    {invoice.customer_name}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {invoice.invoice_number} · {invoiceDueLabel(invoice)}
                  </p>
                </div>
                <p className="tabular-nums text-xs font-semibold">
                  {compactRupiah.format(Number(invoice.total))}
                </p>
                <ArrowUpRight className="size-3.5 text-muted-foreground" />
              </Link>
            ))}
          </div>
        ) : (
          <div className="px-5 py-10 text-center">
            <ReceiptText className="mx-auto size-6 text-muted-foreground" />
            <p className="mt-3 text-sm font-semibold">Tidak ada piutang aktif</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EvidenceCard({ report }: { report: DashboardReport }) {
  const automation = report.automation;
  const reconciliation = report.reconciliation;
  return (
    <Card className="gap-0 py-0 shadow-[0_8px_28px_rgb(17_36_28/0.035)] ring-border">
      <CardHeader className="border-b px-5 py-5">
        <CardTitle>Dasar laporan</CardTitle>
        <CardDescription>Jejak angka dan kesehatan operasi</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-px bg-border p-0">
        <EvidenceItem
          icon={FileCheck2}
          label="Sumber ledger"
          value={`${report.ledger_source_count} jurnal`}
        />
        <EvidenceItem
          icon={Landmark}
          label="Rekonsiliasi"
          value={`${Number(reconciliation.match_rate_percent).toLocaleString("id-ID", { maximumFractionDigits: 1 })}% cocok`}
        />
        <EvidenceItem
          icon={WalletCards}
          label="Biaya AI tercatat"
          value={rupiah.format(Number(automation.estimated_ai_cost_idr))}
        />
        <EvidenceItem
          icon={CalendarRange}
          label="Dihitung"
          value={formatGenerated(report.generated_at)}
        />
      </CardContent>
    </Card>
  );
}

function EvidenceItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Landmark;
  label: string;
  value: string;
}) {
  return (
    <div className="min-h-24 bg-card p-4">
      <Icon className="size-4 text-muted-foreground" />
      <p className="mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="tabular-nums mt-1 text-xs font-semibold sm:text-sm">
        {value}
      </p>
    </div>
  );
}

function DashboardLoading() {
  return (
    <div className="mt-7 space-y-4" aria-label="Memuat laporan" role="status">
      <div className="grid gap-3 md:grid-cols-3">
        {[0, 1, 2].map((item) => (
          <div
            className="h-40 animate-pulse rounded-xl border bg-card"
            key={item}
          />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.65fr_0.65fr]">
        <div className="h-[410px] animate-pulse rounded-xl border bg-card" />
        <div className="h-[410px] animate-pulse rounded-xl border bg-card" />
      </div>
    </div>
  );
}

function DashboardError({
  message,
  retry,
}: {
  message: string;
  retry: () => void;
}) {
  return (
    <Card className="mt-7 py-12 text-center ring-border">
      <CardContent>
        <AlertTriangle className="mx-auto size-6 text-destructive" />
        <p className="mt-3 font-semibold">Laporan belum dapat dimuat</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {message}
        </p>
        <Button className="mt-5" onClick={retry} variant="outline">
          <RefreshCw data-icon="inline-start" />
          Coba lagi
        </Button>
      </CardContent>
    </Card>
  );
}

function buildRanges(): RangeOption[] {
  const today = parseIsoDate(jakartaToday());
  const monthStart = new Date(
    Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1),
  );
  const quarterStart = new Date(
    Date.UTC(
      today.getUTCFullYear(),
      Math.floor(today.getUTCMonth() / 3) * 3,
      1,
    ),
  );
  const last30Start = addDays(today, -29);
  return [
    {
      value: "month",
      label: "Bulan berjalan",
      startDate: toIsoDate(monthStart),
      endDate: toIsoDate(today),
    },
    {
      value: "30-days",
      label: "30 hari terakhir",
      startDate: toIsoDate(last30Start),
      endDate: toIsoDate(today),
    },
    {
      value: "quarter",
      label: "Kuartal berjalan",
      startDate: toIsoDate(quarterStart),
      endDate: toIsoDate(today),
    },
  ];
}

function jakartaToday(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Jakarta",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

function parseIsoDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function toIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(value: Date, days: number): Date {
  const result = new Date(value);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}

function formatShortDate(value: string): string {
  return shortDateLabel.format(parseIsoDate(value));
}

function formatFullDate(value: string): string {
  return dateLabel.format(parseIsoDate(value));
}

function formatPeriod(start: string, end: string): string {
  return `${formatShortDate(start)}–${formatFullDate(end)}`;
}

function formatGenerated(value: string): string {
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Jakarta",
  }).format(new Date(value));
}

function sum(
  points: DashboardReport["cashflow"],
  key: "inflow" | "outflow",
): number {
  return points.reduce((total, point) => total + Number(point[key]), 0);
}

function severityLabel(severity: "HIGH" | "MEDIUM" | "LOW"): string {
  if (severity === "HIGH") return "Mendesak";
  if (severity === "MEDIUM") return "Periksa";
  return "Info";
}

function severityClass(severity: "HIGH" | "MEDIUM" | "LOW"): string {
  if (severity === "HIGH") return "bg-[#f5dfda] text-[#943c31]";
  if (severity === "MEDIUM") return "bg-[#f7eadc] text-[#8a552d]";
  return "bg-muted text-muted-foreground";
}

function invoiceDueLabel(invoice: {
  status: string;
  days_overdue: number;
  due_date: string;
}): string {
  if (invoice.days_overdue > 0) {
    return `terlambat ${invoice.days_overdue} hari`;
  }
  return `jatuh tempo ${formatShortDate(invoice.due_date)}`;
}
