"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Clock3,
  FlaskConical,
  LoaderCircle,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { AppShell, useSessionToken } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
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
import {
  type EvaluationRun,
  type WorkflowReplay,
  getChaosScenarios,
  getEvaluationRuns,
  getWorkflowReplays,
  recoverWorkflow,
  setChaosScenario,
  startEvaluationRun,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type LabTab = "replay" | "evaluation" | "chaos";

const tabs: Array<{ id: LabTab; label: string }> = [
  { id: "replay", label: "Workflow replay" },
  { id: "evaluation", label: "Evaluasi AI" },
  { id: "chaos", label: "Chaos Mode" },
];

const metricLabels: Record<string, string> = {
  exact_total_date_pct: "Total & tanggal",
  category_top1_pct: "Kategori",
  reconciliation_precision_pct: "Rekonsiliasi",
  duplicate_prevention_pct: "Duplikat",
  incomplete_review_pct: "Review dokumen",
};

const chartConfig = {
  current: { label: "Run terbaru", color: "#176b52" },
  previous: { label: "Run pembanding", color: "#c36f3d" },
} satisfies ChartConfig;

export default function ReliabilityPage() {
  const token = useSessionToken();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<LabTab>("replay");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const workflows = useQuery({
    queryKey: ["workflow-replays"],
    queryFn: () => getWorkflowReplays(token!),
    enabled: Boolean(token),
    refetchInterval: 5_000,
  });
  const evaluations = useQuery({
    queryKey: ["evaluation-runs"],
    queryFn: () => getEvaluationRuns(token!),
    enabled: Boolean(token),
    refetchInterval: (query) =>
      query.state.data?.items.some((run) => ["PENDING", "RUNNING"].includes(run.status))
        ? 2_000
        : false,
  });
  const chaos = useQuery({
    queryKey: ["chaos-scenarios"],
    queryFn: () => getChaosScenarios(token!),
    enabled: Boolean(token),
  });

  const recover = useMutation({
    mutationFn: (runId: string) => recoverWorkflow(token!, runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workflow-replays"] }),
  });
  const runEvaluation = useMutation({
    mutationFn: () => {
      const latestPrompt = evaluations.data?.items[0]?.prompt_version;
      return startEvaluationRun(token!, {
        model: "mock-finance-v1",
        prompt_version:
          latestPrompt === "finance-inbox-v1"
            ? "finance-inbox-v2"
            : "finance-inbox-v1",
      });
    },
    onSuccess: () => {
      setTab("evaluation");
      queryClient.invalidateQueries({ queryKey: ["evaluation-runs"] });
    },
  });
  const changeChaos = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      setChaosScenario(token!, key, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chaos-scenarios"] }),
  });

  const effectiveRunId = selectedRunId ?? workflows.data?.items[0]?.id;
  const selectedRun = workflows.data?.items.find((run) => run.id === effectiveRunId);
  const latestEval = evaluations.data?.items.find((run) => run.status === "SUCCEEDED");

  return (
    <AppShell>
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7 sm:py-8 xl:px-10 xl:py-9">
        <header className="flex flex-col gap-5 border-b pb-7 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <p className="eyebrow">Engineering controls</p>
              <Badge variant="outline">Demo environment</Badge>
            </div>
            <h1 className="text-[30px] font-semibold tracking-[-0.045em] sm:text-[36px]">
              Reliability Lab
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Uji kegagalan dengan aman, telusuri keputusan workflow, dan ukur kualitas AI
              sebelum perubahan dipakai dalam operasional.
            </p>
          </div>
          <Button
            disabled={runEvaluation.isPending}
            onClick={() => runEvaluation.mutate()}
            type="button"
          >
            {runEvaluation.isPending ? <LoaderCircle className="animate-spin" /> : <Play />}
            Jalankan evaluasi
          </Button>
        </header>

        <section className="grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 xl:grid-cols-4">
          <SummaryCell
            label="Dead-letter"
            value={String(workflows.data?.dead_letter_count ?? 0)}
            detail="Workflow menunggu recovery"
          />
          <SummaryCell
            label="Golden dataset"
            value={latestEval?.summary.case_count ? `${latestEval.summary.case_count} kasus` : "Belum dijalankan"}
            detail={latestEval?.dataset_version ?? "Sumber evaluasi belum tersedia"}
          />
          <SummaryCell
            label="Safety gate"
            value={latestEval?.summary.target_passed ? "Lulus" : latestEval ? "Perlu tinjauan" : "Belum dinilai"}
            detail={latestEval ? `${latestEval.summary.pass_rate_pct ?? 0}% kasus lulus` : "Jalankan evaluasi pertama"}
          />
          <SummaryCell
            label="AI observability"
            value={latestEval ? `${latestEval.summary.average_latency_ms ?? 0} ms` : "—"}
            detail={latestEval ? `Estimasi $${(latestEval.summary.estimated_cost_usd ?? 0).toFixed(4)}` : "Latensi dan biaya per run"}
          />
        </section>

        <nav aria-label="Reliability Lab sections" className="mt-7 flex gap-1 border-b">
          {tabs.map((item) => (
            <button
              className={cn(
                "relative px-4 pb-3 pt-1 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                tab === item.id && "text-foreground after:absolute after:inset-x-3 after:bottom-[-1px] after:h-0.5 after:bg-primary",
              )}
              key={item.id}
              onClick={() => setTab(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="mt-6">
          {tab === "replay" && (
            <ReplayPanel
              error={workflows.error}
              isLoading={workflows.isPending}
              onRecover={(id) => recover.mutate(id)}
              onSelect={setSelectedRunId}
              recoverPending={recover.isPending}
              runs={workflows.data?.items ?? []}
              selected={selectedRun}
            />
          )}
          {tab === "evaluation" && (
            <EvaluationPanel
              error={evaluations.error}
              isLoading={evaluations.isPending}
              runs={evaluations.data?.items ?? []}
            />
          )}
          {tab === "chaos" && (
            <ChaosPanel
              environment={chaos.data?.environment}
              error={chaos.error}
              isLoading={chaos.isPending}
              isPending={changeChaos.isPending}
              items={chaos.data?.items ?? []}
              onChange={(key, enabled) => changeChaos.mutate({ key, enabled })}
            />
          )}
        </div>
      </main>
    </AppShell>
  );
}

function SummaryCell({ label, value, detail, className }: { label: string; value: string; detail: string; className?: string }) {
  return (
    <div className={cn("bg-card px-5 py-4", className)}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-[-0.025em]">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function ReplayPanel({ runs, selected, onSelect, onRecover, recoverPending, isLoading, error }: {
  runs: WorkflowReplay[];
  selected?: WorkflowReplay;
  onSelect: (id: string) => void;
  onRecover: (id: string) => void;
  recoverPending: boolean;
  isLoading: boolean;
  error: Error | null;
}) {
  if (isLoading) return <LoadingState label="Memuat replay workflow" />;
  if (error) return <ErrorState message={error.message} />;
  if (!runs.length) return <EmptyState title="Belum ada workflow" detail="Upload dokumen untuk melihat replay langkah otomatisasi." />;
  return (
    <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Riwayat workflow</CardTitle>
          <CardDescription>Pilih run untuk melihat langkah, retry, dan keputusan.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1">
          {runs.map((run) => (
            <button
              className={cn("flex w-full items-center gap-3 rounded-lg border border-transparent px-3 py-3 text-left hover:bg-muted/60", selected?.id === run.id && "border-border bg-muted")}
              key={run.id}
              onClick={() => onSelect(run.id)}
              type="button"
            >
              <StatusIcon status={run.status} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">Dokumen {run.entity_id.slice(0, 8)}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{run.status.replaceAll("_", " ")} · {run.retry_count} retry</span>
              </span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>
          ))}
        </CardContent>
      </Card>
      {selected && (
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardTitle>Complete automation replay</CardTitle>
                  <CardDescription className="mt-1 font-mono text-[11px]">{selected.correlation_id}</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{selected.status.replaceAll("_", " ")}</Badge>
                  {["FAILED", "DEAD_LETTER"].includes(selected.status) && (
                    <Button disabled={recoverPending} onClick={() => onRecover(selected.id)} size="sm" type="button">
                      <RotateCcw /> Pulihkan
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {selected.safe_error && (
                <div className="mb-5 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-950">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <div><p className="text-sm font-medium">{selected.safe_error}</p><p className="mt-1 text-xs text-amber-800">Recovery melanjutkan dari langkah aman dan mempertahankan output yang sudah berhasil.</p></div>
                </div>
              )}
              <ol className="divide-y">
                {selected.steps.map((step) => (
                  <li className="grid gap-2 py-4 sm:grid-cols-[36px_minmax(0,1fr)_120px] sm:items-center" key={step.id}>
                    <span className="grid size-7 place-items-center rounded-md border text-xs font-semibold">{step.sequence}</span>
                    <div><p className="text-sm font-medium capitalize">{step.name.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-muted-foreground">{step.error_code ?? summarizeOutput(step.output)}</p></div>
                    <div className="text-left sm:text-right"><Badge variant="outline">{step.status}</Badge><p className="mt-1 text-[11px] text-muted-foreground">{formatDuration(step.duration_ms)}</p></div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card><CardHeader><CardTitle>Retry attempts</CardTitle><CardDescription>Backoff dan titik resume setiap percobaan.</CardDescription></CardHeader><CardContent>{selected.attempts.length ? <div className="divide-y">{selected.attempts.map((attempt) => <div className="flex items-center justify-between py-3 text-sm" key={attempt.id}><div><p className="font-medium">Percobaan {attempt.number}</p><p className="mt-0.5 text-xs text-muted-foreground">Resume dari langkah {attempt.safe_resume_sequence}</p></div><div className="text-right"><p className="text-xs font-medium">{attempt.status}</p><p className="mt-0.5 text-xs text-muted-foreground">{attempt.retry_delay_seconds ? `Retry ${attempt.retry_delay_seconds} dtk` : formatDuration(attempt.duration_ms)}</p></div></div>)}</div> : <p className="text-sm text-muted-foreground">Run lama belum memiliki rekaman attempt.</p>}</CardContent></Card>
            <Card><CardHeader><CardTitle>Decision log</CardTitle><CardDescription>Audit event untuk run ini.</CardDescription></CardHeader><CardContent className="max-h-72 overflow-auto"><div className="divide-y">{selected.decisions.slice().reverse().map((decision) => <div className="py-3" key={decision.id}><p className="text-sm font-medium">{decision.action.replaceAll(".", " ")}</p><p className="mt-1 text-xs text-muted-foreground">{new Date(decision.created_at).toLocaleString("id-ID")}</p></div>)}</div></CardContent></Card>
          </div>
        </div>
      )}
    </div>
  );
}

function EvaluationPanel({ runs, isLoading, error }: { runs: EvaluationRun[]; isLoading: boolean; error: Error | null }) {
  const completed = runs.filter((run) => run.status === "SUCCEEDED").slice(0, 2);
  const chartData = useMemo(() => Object.entries(metricLabels).map(([key, label]) => ({ metric: label, current: completed[0]?.summary.metrics?.[key] ?? 0, previous: completed[1]?.summary.metrics?.[key] ?? 0 })), [completed]);
  if (isLoading) return <LoadingState label="Memuat hasil evaluasi" />;
  if (error) return <ErrorState message={error.message} />;
  if (!runs.length) return <EmptyState title="Belum ada hasil evaluasi" detail="Jalankan golden dataset untuk membuat baseline kualitas pertama." />;
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Card>
        <CardHeader><CardTitle>Perbandingan kualitas</CardTitle><CardDescription>Lima metrik persentase dari dua run terbaru. Semua angka bersumber dari golden dataset.</CardDescription></CardHeader>
        <CardContent>
          {completed.length < 2 && <div className="mb-4 rounded-lg border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">Jalankan satu evaluasi lagi untuk mengaktifkan perbandingan dua versi.</div>}
          <ChartContainer className="h-[330px] w-full aspect-auto" config={chartConfig}>
            <BarChart accessibilityLayer data={chartData} margin={{ left: 0, right: 12 }}>
              <CartesianGrid vertical={false} />
              <XAxis axisLine={false} dataKey="metric" tickLine={false} tickMargin={10} />
              <YAxis axisLine={false} domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} width={40} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="current" fill="var(--color-current)" radius={[3, 3, 0, 0]} />
              <Bar dataKey="previous" fill="var(--color-previous)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartContainer>
          {completed[0] && <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">Sumber: {completed[0].summary.source} · Dataset {completed[0].dataset_version}</p>}
        </CardContent>
      </Card>
      <div className="space-y-4">
        {runs.map((run, index) => (
          <Card key={run.id}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3"><div><CardTitle className="text-base">{index === 0 ? "Run terbaru" : `Run ${runs.length - index}`}</CardTitle><CardDescription>{run.model} · {run.prompt_version}</CardDescription></div><Badge variant="outline">{run.status}</Badge></div>
            </CardHeader>
            <CardContent>
              {run.status === "SUCCEEDED" ? <div className="grid grid-cols-3 gap-3"><MetricMini label="Pass rate" value={`${run.summary.pass_rate_pct ?? 0}%`} /><MetricMini label="Latensi" value={`${run.summary.average_latency_ms ?? 0} ms`} /><MetricMini label="Biaya" value={`$${(run.summary.estimated_cost_usd ?? 0).toFixed(4)}`} /></div> : <div className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className={cn("size-4", run.status !== "FAILED" && "animate-spin")} />Evaluasi sedang diproses.</div>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function ChaosPanel({ items, environment, isLoading, isPending, error, onChange }: { items: Array<{ key: string; name: string; description: string; recovery: string; available: boolean; enabled: boolean; trigger_count: number }>; environment?: string; isLoading: boolean; isPending: boolean; error: Error | null; onChange: (key: string, enabled: boolean) => void }) {
  if (isLoading) return <LoadingState label="Memuat Chaos Mode" />;
  if (error) return <ErrorState message={error.message} />;
  return (
    <div>
      <div className="mb-5 flex gap-3 rounded-lg border bg-muted/40 p-4"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" /><div><p className="text-sm font-medium">Terisolasi untuk demo dan development</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Environment: {environment ?? "unknown"}. Hanya satu skenario dapat aktif dan seluruh perubahan tercatat di audit log. Chaos Mode ditolak di production.</p></div></div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((scenario) => (
          <Card className={cn(scenario.enabled && "border-primary/50")} key={scenario.key}>
            <CardHeader><div className="flex items-start justify-between gap-4"><div><CardTitle className="text-base">{scenario.name}</CardTitle><CardDescription className="mt-1 leading-5">{scenario.description}</CardDescription></div><Badge variant={scenario.enabled ? "default" : "outline"}>{scenario.enabled ? "Aktif" : "Nonaktif"}</Badge></div></CardHeader>
            <CardContent><div className="min-h-14 border-l-2 border-border pl-3"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Recovery</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{scenario.recovery}</p></div><div className="mt-5 flex items-center justify-between"><p className="text-xs text-muted-foreground">Dipicu {scenario.trigger_count} kali</p><Button disabled={isPending || !scenario.available} onClick={() => onChange(scenario.key, !scenario.enabled)} size="sm" type="button" variant={scenario.enabled ? "outline" : "default"}>{scenario.enabled ? "Nonaktifkan" : "Aktifkan"}</Button></div></CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (["SUCCEEDED", "WAITING_FOR_APPROVAL"].includes(status)) return <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700"><Check className="size-4" /></span>;
  if (["FAILED", "DEAD_LETTER"].includes(status)) return <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-amber-50 text-amber-700"><AlertTriangle className="size-4" /></span>;
  return <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground"><Clock3 className="size-4" /></span>;
}

function MetricMini({ label, value }: { label: string; value: string }) { return <div><p className="text-[11px] text-muted-foreground">{label}</p><p className="mt-1 text-sm font-semibold">{value}</p></div>; }
function LoadingState({ label }: { label: string }) { return <div className="grid min-h-64 place-items-center rounded-xl border bg-card"><div className="text-center"><LoaderCircle className="mx-auto size-5 animate-spin text-primary" /><p className="mt-3 text-sm text-muted-foreground">{label}</p></div></div>; }
function ErrorState({ message }: { message: string }) { return <div className="flex min-h-40 items-center justify-center rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive"><AlertTriangle className="mr-2 size-4" />{message}</div>; }
function EmptyState({ title, detail }: { title: string; detail: string }) { return <div className="grid min-h-64 place-items-center rounded-xl border bg-card p-8 text-center"><div><FlaskConical className="mx-auto size-6 text-muted-foreground" /><h2 className="mt-3 text-sm font-semibold">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{detail}</p></div></div>; }
function formatDuration(value: number | null): string { return value === null ? "Belum selesai" : value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} dtk`; }
function summarizeOutput(output: Record<string, unknown>): string { const entries = Object.entries(output); if (!entries.length) return "Belum ada output"; return entries.slice(0, 2).map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`).join(" · "); }
