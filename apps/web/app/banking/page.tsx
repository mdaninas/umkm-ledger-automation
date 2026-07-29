"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ChangeEvent, FormEvent, useState } from "react";
import { AppShell, useSessionToken } from "@/components/app-shell";
import {
  ApiError,
  BankColumnMapping,
  BankImport,
  BankTransaction,
  BankTransactionStatus,
  confirmReconciliation,
  getBankImports,
  getBankTransactions,
  rejectReconciliation,
  uploadBankImport,
} from "@/lib/api";

const rupiah = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

type AmountMode = "split" | "signed";

export default function BankingPage() {
  const token = useSessionToken();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<BankColumnMapping>({
    date: "",
    description: "",
    debit: "",
    credit: "",
  });
  const [amountMode, setAmountMode] = useState<AmountMode>("split");
  const [importResult, setImportResult] = useState<BankImport | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const imports = useQuery({
    queryKey: ["bank-imports"],
    queryFn: () => getBankImports(token!),
    enabled: Boolean(token),
  });
  const transactions = useQuery({
    queryKey: ["bank-transactions", status, search],
    queryFn: () => getBankTransactions(token!, { status, search }),
    enabled: Boolean(token),
  });
  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Pilih file CSV.");
      return uploadBankImport(token!, file, cleanMapping(mapping, amountMode));
    },
    onSuccess: (result) => {
      setImportResult(result);
      queryClient.invalidateQueries({ queryKey: ["bank-imports"] });
      queryClient.invalidateQueries({ queryKey: ["bank-transactions"] });
    },
  });

  const items = transactions.data?.items ?? [];
  const selected =
    items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const latestImport = importResult ?? imports.data?.items[0] ?? null;
  const mappingReady = Boolean(
    file &&
      mapping.date &&
      mapping.description &&
      (amountMode === "signed"
        ? mapping.amount
        : mapping.debit && mapping.credit),
  );

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0] ?? null;
    setFile(selectedFile);
    setImportResult(null);
    upload.reset();
    if (!selectedFile) {
      setHeaders([]);
      return;
    }
    const text = await selectedFile.text();
    const detectedHeaders = parseCsvHeader(text);
    const detected = detectMapping(detectedHeaders);
    setHeaders(detectedHeaders);
    setAmountMode(detected.amount ? "signed" : "split");
    setMapping(detected);
  }

  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mappingReady) upload.mutate();
  }

  return (
    <AppShell>
      <main className="mx-auto max-w-[1320px] px-5 py-7 sm:px-8 sm:py-9 xl:px-10">
        <header className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
          <div>
            <p className="eyebrow text-[#8a6a51]">Rekonsiliasi</p>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] sm:text-[28px]">
              Mutasi bank
            </h1>
            <p className="mt-1.5 max-w-2xl text-sm text-[#69716c]">
              Impor transaksi, lihat alasan setiap skor, lalu putuskan kandidat
              yang ambigu.
            </p>
          </div>
          <a
            className="secondary-button self-start sm:self-auto"
            download
            href="/samples/kopi-arunika-july-2026.csv"
          >
            <DownloadIcon />
            Unduh sample CSV
          </a>
        </header>

        <section className="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,.75fr)]">
          <form className="app-card overflow-hidden" onSubmit={submitImport}>
            <div className="flex items-start justify-between border-b border-[#e4dacd] bg-[#fffaf3] px-5 py-4 sm:px-6">
              <div>
                <h2 className="text-sm font-semibold">Impor mutasi CSV</h2>
                <p className="mt-1 text-xs text-[#777e79]">
                  File UTF-8, maksimal 10 MB
                </p>
              </div>
              <span className="rounded-full bg-[#e5f0e9] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#276247]">
                Read-only
              </span>
            </div>
            <div className="p-5 sm:p-6">
              <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-dashed border-[#cbbfaf] bg-[#f8f2e9] p-4 transition hover:border-[#9c8b75]">
                <span className="flex min-w-0 items-center gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[#173f32] text-white">
                    <UploadIcon />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">
                      {file?.name ?? "Pilih file mutasi"}
                    </span>
                    <span className="mt-0.5 block text-xs text-[#69716c]">
                      {file
                        ? `${headers.length} kolom terdeteksi`
                        : "Klik untuk memilih file .csv"}
                    </span>
                  </span>
                </span>
                <span className="text-xs font-semibold text-[#174d3a]">
                  {file ? "Ganti" : "Pilih"}
                </span>
                <input
                  accept=".csv,text/csv"
                  className="sr-only"
                  onChange={handleFile}
                  type="file"
                />
              </label>

              {file ? (
                <div className="mt-5">
                  <div className="mb-3 flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
                    <div>
                      <p className="text-sm font-semibold">Mapping kolom</p>
                      <p className="mt-0.5 text-xs text-[#777e79]">
                        Pastikan arti kolom sesuai sebelum mengimpor.
                      </p>
                    </div>
                    <label className="min-w-48 text-xs font-medium">
                      Format nominal
                      <select
                        className="form-control mt-1.5"
                        onChange={(event) => {
                          const nextMode = event.target.value as AmountMode;
                          setAmountMode(nextMode);
                          setMapping((current) =>
                            nextMode === "signed"
                              ? {
                                  date: current.date,
                                  description: current.description,
                                  amount: current.amount ?? "",
                                  reference: current.reference,
                                }
                              : {
                                  date: current.date,
                                  description: current.description,
                                  debit: current.debit ?? "",
                                  credit: current.credit ?? "",
                                  reference: current.reference,
                                },
                          );
                        }}
                        value={amountMode}
                      >
                        <option value="split">Debit dan kredit terpisah</option>
                        <option value="signed">Satu kolom nominal</option>
                      </select>
                    </label>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <ColumnSelect
                      headers={headers}
                      label="Tanggal"
                      onChange={(value) =>
                        setMapping((current) => ({ ...current, date: value }))
                      }
                      required
                      value={mapping.date}
                    />
                    <ColumnSelect
                      headers={headers}
                      label="Deskripsi"
                      onChange={(value) =>
                        setMapping((current) => ({
                          ...current,
                          description: value,
                        }))
                      }
                      required
                      value={mapping.description}
                    />
                    {amountMode === "signed" ? (
                      <ColumnSelect
                        headers={headers}
                        label="Nominal"
                        onChange={(value) =>
                          setMapping((current) => ({
                            ...current,
                            amount: value,
                          }))
                        }
                        required
                        value={mapping.amount ?? ""}
                      />
                    ) : (
                      <>
                        <ColumnSelect
                          headers={headers}
                          label="Debit"
                          onChange={(value) =>
                            setMapping((current) => ({
                              ...current,
                              debit: value,
                            }))
                          }
                          required
                          value={mapping.debit ?? ""}
                        />
                        <ColumnSelect
                          headers={headers}
                          label="Kredit"
                          onChange={(value) =>
                            setMapping((current) => ({
                              ...current,
                              credit: value,
                            }))
                          }
                          required
                          value={mapping.credit ?? ""}
                        />
                      </>
                    )}
                    <ColumnSelect
                      headers={headers}
                      label="Referensi"
                      onChange={(value) =>
                        setMapping((current) => ({
                          ...current,
                          reference: value || undefined,
                        }))
                      }
                      value={mapping.reference ?? ""}
                    />
                  </div>

                  {upload.isError ? (
                    <p className="mt-4 rounded-lg border border-[#e3b7af] bg-[#fbeeea] px-3.5 py-3 text-sm text-[#8d3a30]">
                      {upload.error instanceof ApiError
                        ? upload.error.message
                        : "Impor belum berhasil. Periksa file dan mapping kolom."}
                    </p>
                  ) : null}

                  <div className="mt-5 flex items-center justify-between gap-4 border-t border-[#e4dacd] pt-4">
                    <p className="text-xs leading-5 text-[#69716c]">
                      File yang sama tidak akan menambah transaksi ganda.
                    </p>
                    <button
                      className="primary-button shrink-0"
                      disabled={!mappingReady || upload.isPending}
                      type="submit"
                    >
                      {upload.isPending ? "Mengimpor…" : "Impor transaksi"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </form>

          <ImportSummary bankImport={latestImport} loading={imports.isPending} />
        </section>

        <TransactionOverview
          counts={
            transactions.data?.counts ?? {
              total: 0,
              unmatched: 0,
              suggested: 0,
              matched: 0,
            }
          }
          loading={transactions.isPending}
        />

        <section className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(390px,.8fr)]">
          <div className="app-card overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-[#e4dacd] bg-[#fffaf3] p-3 sm:flex-row">
              <label className="relative flex-1">
                <SearchIcon />
                <span className="sr-only">Cari transaksi bank</span>
                <input
                  className="form-control !pl-10"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Cari deskripsi atau referensi"
                  type="search"
                  value={search}
                />
              </label>
              <label>
                <span className="sr-only">Filter status transaksi</span>
                <select
                  className="form-control min-w-48"
                  onChange={(event) => setStatus(event.target.value)}
                  value={status}
                >
                  <option value="">Semua status</option>
                  <option value="SUGGESTED">Perlu keputusan</option>
                  <option value="UNMATCHED">Belum cocok</option>
                  <option value="AUTO_MATCHED">Cocok otomatis</option>
                  <option value="CONFIRMED">Dikonfirmasi</option>
                </select>
              </label>
            </div>
            <div className="hidden grid-cols-[110px_minmax(220px,1fr)_130px_135px] gap-4 border-b border-[#e4dacd] bg-[#f8f2e9] px-4 py-2.5 text-[11px] font-medium text-[#777e79] md:grid">
              <span>Tanggal</span>
              <span>Transaksi</span>
              <span className="text-right">Nominal</span>
              <span>Status</span>
            </div>
            {transactions.isPending ? (
              <div className="grid min-h-64 place-items-center text-sm text-[#69716c]">
                Memuat transaksi…
              </div>
            ) : items.length ? (
              <div className="divide-y divide-[#eadfd2]">
                {items.map((transaction) => (
                  <button
                    className={`grid w-full gap-3 px-4 py-4 text-left transition md:grid-cols-[110px_minmax(220px,1fr)_130px_135px] md:items-center ${
                      selectedId === transaction.id
                        ? "bg-[#f4eadb]"
                        : "hover:bg-[#fbf6ee]"
                    }`}
                    key={transaction.id}
                    onClick={() => setSelectedId(transaction.id)}
                    type="button"
                  >
                    <p className="text-xs text-[#69716c]">
                      {new Date(transaction.transaction_date).toLocaleDateString(
                        "id-ID",
                        { day: "2-digit", month: "short", year: "numeric" },
                      )}
                    </p>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {transaction.description}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-[#777e79]">
                        {transaction.reference ?? "Tanpa referensi"}
                      </p>
                    </div>
                    <p
                      className={`tabular-nums text-sm font-semibold md:text-right ${
                        transaction.direction === "DEBIT"
                          ? "text-[#a44e2b]"
                          : "text-[#276247]"
                      }`}
                    >
                      {transaction.direction === "DEBIT" ? "−" : "+"}
                      {rupiah.format(Number(transaction.amount))}
                    </p>
                    <BankStatus status={transaction.status} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="grid min-h-72 place-items-center p-8 text-center">
                <div>
                  <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-[#f3ece2] text-[#58635d]">
                    <BankIcon />
                  </span>
                  <p className="mt-4 text-sm font-semibold">
                    Belum ada transaksi bank
                  </p>
                  <p className="mt-1.5 text-sm text-[#69716c]">
                    Impor sample CSV untuk memulai rekonsiliasi.
                  </p>
                </div>
              </div>
            )}
          </div>

          <CandidatePanel
            key={selected?.id ?? "no-transaction"}
            queryClient={queryClient}
            token={token}
            transaction={selected}
          />
        </section>
      </main>
    </AppShell>
  );
}

function ImportSummary({
  bankImport,
  loading,
}: {
  bankImport: BankImport | null;
  loading: boolean;
}) {
  return (
    <aside className="app-card overflow-hidden">
      <div className="border-b border-[#e4dacd] bg-[#173f32] px-5 py-4 text-white">
        <p className="text-sm font-semibold">Impor terakhir</p>
        <p className="mt-1 truncate text-xs text-[#b9cbc3]">
          {bankImport?.filename ?? (loading ? "Memuat…" : "Belum ada file")}
        </p>
      </div>
      {bankImport ? (
        <div className="p-5">
          {bankImport.duplicate_file ? (
            <p className="mb-4 rounded-lg bg-[#f7e3d5] px-3 py-2.5 text-xs font-medium text-[#7d4028]">
              File sudah pernah diimpor. Tidak ada transaksi baru.
            </p>
          ) : null}
          <div className="grid grid-cols-2 gap-x-5 gap-y-4">
            <MiniStat label="Baris CSV" value={bankImport.row_count} />
            <MiniStat label="Berhasil" value={bankImport.imported_count} />
            <MiniStat label="Duplikat" value={bankImport.duplicate_count} />
            <MiniStat label="Gagal" value={bankImport.error_count} />
          </div>
          <p className="mt-5 border-t border-[#e4dacd] pt-4 text-xs text-[#69716c]">
            {new Date(bankImport.created_at).toLocaleString("id-ID", {
              day: "2-digit",
              month: "short",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
          {bankImport.row_errors.length ? (
            <div className="mt-4 rounded-lg border border-[#e2bfaa] bg-[#fff7ef] p-3">
              <p className="text-xs font-semibold text-[#7d4028]">
                Baris yang perlu diperbaiki
              </p>
              <ul className="mt-2 space-y-1.5 text-xs leading-5 text-[#86543d]">
                {bankImport.row_errors.slice(0, 3).map((error) => (
                  <li key={`${error.row}-${error.code}`}>
                    Baris {error.row}: {error.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="grid min-h-52 place-items-center px-5 text-center text-sm text-[#69716c]">
          Ringkasan hasil impor akan tampil di sini.
        </div>
      )}
    </aside>
  );
}

function TransactionOverview({
  counts,
  loading,
}: {
  counts: { total: number; unmatched: number; suggested: number; matched: number };
  loading: boolean;
}) {
  const stats = [
    { label: "Total transaksi", value: counts.total },
    { label: "Perlu keputusan", value: counts.suggested },
    { label: "Belum cocok", value: counts.unmatched },
    { label: "Sudah cocok", value: counts.matched },
  ];
  return (
    <section className="app-card mt-5 grid overflow-hidden sm:grid-cols-2 xl:grid-cols-4">
      {stats.map((stat, index) => (
        <div
          className={`border-[#e4dacd] px-5 py-4 ${
            index ? "border-t sm:border-l sm:border-t-0" : ""
          } ${index === 2 ? "sm:border-l-0 sm:border-t xl:border-l xl:border-t-0" : ""}`}
          key={stat.label}
        >
          <p className="text-xs text-[#69716c]">{stat.label}</p>
          <p className="tabular-nums mt-1 text-xl font-semibold">
            {loading ? "—" : stat.value}
          </p>
        </div>
      ))}
    </section>
  );
}

function CandidatePanel({
  token,
  transaction,
  queryClient,
}: {
  token: string | null;
  transaction: BankTransaction | null;
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  const [comment, setComment] = useState("");
  const confirm = useMutation({
    mutationFn: (candidateId: string) =>
      confirmReconciliation(token!, candidateId, comment),
    onSuccess: () => {
      setComment("");
      queryClient.invalidateQueries({ queryKey: ["bank-transactions"] });
    },
  });
  const reject = useMutation({
    mutationFn: (candidateId: string) =>
      rejectReconciliation(token!, candidateId, comment),
    onSuccess: () => {
      setComment("");
      queryClient.invalidateQueries({ queryKey: ["bank-transactions"] });
    },
  });
  const error = confirm.error ?? reject.error;

  if (!transaction) {
    return (
      <aside className="app-card grid min-h-80 place-items-center p-8 text-center">
        <div>
          <p className="text-sm font-semibold">Pilih transaksi</p>
          <p className="mt-1.5 text-sm text-[#69716c]">
            Breakdown skor akan tampil di panel ini.
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="app-card overflow-hidden xl:sticky xl:top-5">
      <div className="border-b border-[#e4dacd] bg-[#173f32] px-5 py-4 text-white">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {transaction.description}
            </p>
            <p className="mt-1 text-xs text-[#b9cbc3]">
              {rupiah.format(Number(transaction.amount))} ·{" "}
              {transaction.direction === "DEBIT" ? "Dana keluar" : "Dana masuk"}
            </p>
          </div>
          <BankStatus dark status={transaction.status} />
        </div>
      </div>

      {transaction.candidates.length ? (
        <div className="divide-y divide-[#e4dacd]">
          {transaction.candidates.map((candidate) => {
            const actionable = ["SUGGESTED", "AUTO_MATCHED"].includes(
              candidate.status,
            );
            return (
              <article className="p-5" key={candidate.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">
                      {candidate.source.vendor_name ?? "Dokumen tanpa vendor"}
                    </p>
                    <Link
                      className="mt-1 block truncate text-xs font-medium text-[#2c7356] hover:underline"
                      href={`/inbox/${candidate.source.id}`}
                    >
                      {candidate.source.document_number ?? "Buka dokumen sumber"} →
                    </Link>
                  </div>
                  <div className="text-right">
                    <p className="tabular-nums text-2xl font-semibold text-[#173f32]">
                      {Math.round(Number(candidate.score))}
                    </p>
                    <p className="text-[10px] uppercase tracking-wide text-[#777e79]">
                      dari 100
                    </p>
                  </div>
                </div>

                <div className="mt-5 space-y-4">
                  {(
                    [
                      ["amount", "Nominal"],
                      ["date", "Tanggal"],
                      ["vendor", "Pihak"],
                      ["reference", "Referensi"],
                    ] as const
                  ).map(([key, label]) => (
                    <ScoreRow
                      component={candidate.score_breakdown[key]}
                      key={key}
                      label={label}
                    />
                  ))}
                </div>

                {candidate.score_breakdown.policy.conflicts.length ? (
                  <div className="mt-5 rounded-lg border border-[#e2bfaa] bg-[#fff7ef] p-3 text-xs leading-5 text-[#7d4028]">
                    <p className="font-semibold">Mengapa perlu review?</p>
                    {candidate.score_breakdown.policy.conflicts.map((conflict) => (
                      <p className="mt-1" key={conflict}>
                        {conflict}
                      </p>
                    ))}
                  </div>
                ) : null}

                <div className="mt-5 flex items-center justify-between border-t border-[#e4dacd] pt-4">
                  <CandidateStatus status={candidate.status} />
                  <p className="text-[10px] text-[#777e79]">
                    Auto-match ≥{" "}
                    {candidate.score_breakdown.policy.auto_match_threshold}
                  </p>
                </div>

                {actionable ? (
                  <div className="mt-4">
                    <label className="text-xs font-medium">
                      Catatan keputusan
                      <textarea
                        className="form-control mt-1.5 min-h-20 resize-y"
                        onChange={(event) => setComment(event.target.value)}
                        placeholder="Tambahkan alasan konfirmasi atau penolakan"
                        value={comment}
                      />
                    </label>
                    {error ? (
                      <p className="mt-2 text-xs text-[#963d32]">
                        {error instanceof ApiError
                          ? error.message
                          : "Keputusan belum dapat disimpan."}
                      </p>
                    ) : null}
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <button
                        className="secondary-button"
                        disabled={!comment.trim() || reject.isPending}
                        onClick={() => reject.mutate(candidate.id)}
                        type="button"
                      >
                        Tolak kandidat
                      </button>
                      <button
                        className="primary-button"
                        disabled={confirm.isPending || reject.isPending}
                        onClick={() => confirm.mutate(candidate.id)}
                        type="button"
                      >
                        Konfirmasi
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="grid min-h-80 place-items-center p-8 text-center">
          <div>
            <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-[#f3ece2] text-[#58635d]">
              <SearchDocumentIcon />
            </span>
            <p className="mt-4 text-sm font-semibold">Belum menemukan pasangan</p>
            <p className="mt-1.5 text-sm leading-6 text-[#69716c]">
              Tidak ada dokumen dengan skor minimal 70. Transaksi tetap berada di
              antrean unmatched.
            </p>
          </div>
        </div>
      )}
    </aside>
  );
}

function ColumnSelect({
  label,
  headers,
  value,
  onChange,
  required = false,
}: {
  label: string;
  headers: string[];
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <label className="text-xs font-medium">
      {label}
      {required ? <span className="text-[#b65431]"> *</span> : null}
      <select
        className="form-control mt-1.5"
        onChange={(event) => onChange(event.target.value)}
        required={required}
        value={value}
      >
        <option value="">Pilih kolom</option>
        {headers.map((header) => (
          <option key={header} value={header}>
            {header}
          </option>
        ))}
      </select>
    </label>
  );
}

function ScoreRow({
  label,
  component,
}: {
  label: string;
  component: { score: string; max_score: string; explanation: string };
}) {
  const percentage =
    (Number(component.score) / Math.max(Number(component.max_score), 1)) * 100;
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums font-semibold">
          {component.score}/{component.max_score}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#eee7dc]">
        <div
          className="h-full rounded-full bg-[#d56f3a]"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="mt-1.5 text-[11px] leading-4 text-[#777e79]">
        {component.explanation}
      </p>
    </div>
  );
}

function BankStatus({
  status,
  dark = false,
}: {
  status: BankTransactionStatus;
  dark?: boolean;
}) {
  const config = {
    UNMATCHED: ["Belum cocok", "bg-[#f0ebe3] text-[#645d54]"],
    SUGGESTED: ["Perlu keputusan", "bg-[#f7e3d5] text-[#874326]"],
    AUTO_MATCHED: ["Cocok otomatis", "bg-[#e5f0e9] text-[#276247]"],
    CONFIRMED: ["Dikonfirmasi", "bg-[#dcece4] text-[#20543c]"],
  }[status];
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold ${
        dark ? "bg-white/12 text-white" : config[1]
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          dark ? "bg-[#e28a53]" : "bg-current"
        }`}
      />
      {config[0]}
    </span>
  );
}

function CandidateStatus({ status }: { status: string }) {
  const labels: Record<string, string> = {
    SUGGESTED: "Menunggu keputusan",
    AUTO_MATCHED: "Dicocokkan otomatis",
    CONFIRMED: "Dikonfirmasi manual",
    REJECTED: "Kandidat ditolak",
  };
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#5f6762]">
      <span className="status-dot text-[#d56f3a]" />
      {labels[status] ?? status}
    </span>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-xs text-[#69716c]">{label}</p>
      <p className="tabular-nums mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function cleanMapping(
  mapping: BankColumnMapping,
  mode: AmountMode,
): BankColumnMapping {
  return mode === "signed"
    ? {
        date: mapping.date,
        description: mapping.description,
        amount: mapping.amount!,
        ...(mapping.reference ? { reference: mapping.reference } : {}),
      }
    : {
        date: mapping.date,
        description: mapping.description,
        debit: mapping.debit!,
        credit: mapping.credit!,
        ...(mapping.reference ? { reference: mapping.reference } : {}),
      };
}

function detectMapping(headers: string[]): BankColumnMapping {
  const find = (...aliases: string[]) =>
    headers.find((header) => aliases.includes(header.toLowerCase())) ?? "";
  const amount = find("amount", "nominal", "jumlah");
  return {
    date: find("tanggal", "date", "transaction_date"),
    description: find("deskripsi", "description", "keterangan"),
    ...(amount
      ? { amount }
      : {
          debit: find("debit", "pengeluaran"),
          credit: find("kredit", "credit", "pemasukan"),
        }),
    reference:
      find("referensi", "reference", "ref", "nomor_referensi") || undefined,
  };
}

function parseCsvHeader(content: string): string[] {
  const line = content.replace(/^\uFEFF/, "").split(/\r?\n/, 1)[0] ?? "";
  const headers: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      headers.push(current.trim());
      current = "";
    } else {
      current += character;
    }
  }
  headers.push(current.trim());
  return headers.filter(Boolean);
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

function UploadIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="17" viewBox="0 0 24 24" width="17">
      <path d="M12 16V4m0 0L7 9m5-5 5 5M5 15v5h14v-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 24 24" width="16">
      <path d="M12 4v12m0 0 5-5m-5 5-5-5M5 20h14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function BankIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="18" viewBox="0 0 24 24" width="18">
      <path d="m3 9 9-5 9 5M5 10h14M6 10v7m4-7v7m4-7v7m4-7v7M4 20h16" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function SearchDocumentIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="18" viewBox="0 0 24 24" width="18">
      <path d="M5 3h9l4 4v7M14 3v5h4M10 20H5V3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      <circle cx="16" cy="17" r="3" stroke="currentColor" strokeWidth="1.7" />
      <path d="m18.5 19.5 2 2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}
