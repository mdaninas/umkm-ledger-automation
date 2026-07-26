"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import {
  getHealth,
  getProfile,
  HealthComponent,
  sessionStorage,
} from "@/lib/api";

const componentLabels: Record<string, string> = {
  api: "API",
  database: "PostgreSQL",
  redis: "Redis",
  object_storage: "MinIO",
  worker: "Celery worker",
};

const subscribeToSession = () => () => undefined;

function HealthBadge({ component }: { component: HealthComponent }) {
  const healthy = component.status === "healthy";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold ${
        healthy
          ? "bg-[#e8f5ce] text-[#35580e]"
          : component.status === "skipped"
            ? "bg-[#ecebe6] text-[#62645f]"
            : "bg-[#fff0eb] text-[#8a321c]"
      }`}
    >
      <span aria-hidden="true">{healthy ? "✓" : component.status === "skipped" ? "–" : "!"}</span>
      {healthy ? "Sehat" : component.status === "skipped" ? "Dilewati" : "Perlu perhatian"}
    </span>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const token = useSyncExternalStore(
    subscribeToSession,
    sessionStorage.getToken,
    () => null,
  );

  useEffect(() => {
    if (!token) router.replace("/login");
  }, [router, token]);

  const profile = useQuery({
    queryKey: ["session-profile"],
    queryFn: () => getProfile(token!),
    enabled: Boolean(token),
    retry: false,
  });
  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: getHealth,
    refetchInterval: 15_000,
  });

  useEffect(() => {
    if (profile.isError) {
      sessionStorage.clear();
      router.replace("/login");
    }
  }, [profile.isError, router]);

  function logout() {
    sessionStorage.clear();
    router.replace("/login");
  }

  if (profile.isPending) {
    return (
      <main className="grid min-h-screen place-items-center p-6">
        <div className="text-center" role="status">
          <div className="mx-auto mb-4 h-9 w-9 animate-spin rounded-full border-4 border-[#dbe6c4] border-t-[#153e2d]" />
          <p className="font-semibold">Menyiapkan ruang kerja…</p>
        </div>
      </main>
    );
  }

  if (!token || !profile.data) return null;

  const healthyCount = health.data
    ? Object.values(health.data.components).filter((item) => item.status === "healthy").length
    : 0;
  const totalComponents = health.data ? Object.keys(health.data.components).length : 5;

  return (
    <main className="min-h-screen bg-[#f7f5ef]">
      <header className="border-b border-[#dcd8cd] bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <Link className="flex items-center gap-3" href="/dashboard">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#153e2d] font-black text-[#c8ef78]">
              KA
            </span>
            <div>
              <p className="font-bold leading-5">{profile.data.business.name}</p>
              <p className="text-xs text-[#718078]">Finance Autopilot</p>
            </div>
          </Link>
          <div className="flex items-center gap-4">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold">{profile.data.user.display_name}</p>
              <p className="text-xs capitalize text-[#718078]">{profile.data.role}</p>
            </div>
            <button
              className="rounded-xl border border-[#d2cec2] bg-white px-4 py-2 text-sm font-semibold transition hover:bg-[#f4f2ec]"
              onClick={logout}
              type="button"
            >
              Keluar
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-[#708269]">
              Foundation console
            </p>
            <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-0.045em] sm:text-5xl">
              Fondasi aman sebelum automation bekerja.
            </h1>
            <p className="mt-4 max-w-2xl text-lg leading-8 text-[#65716b]">
              Login demo, tenant isolation, audit, database migration, dan layanan lokal
              sudah memiliki tempatnya. Fitur dokumen sengaja menunggu MVP 1.
            </p>
          </div>
          <div className="rounded-2xl border border-[#d8d2c2] bg-white px-5 py-4">
            <p className="text-xs font-bold uppercase tracking-wider text-[#718078]">
              Bisnis aktif
            </p>
            <p className="mt-1 font-bold">{profile.data.business.name}</p>
            <p className="text-sm text-[#718078]">
              {profile.data.business.currency} · {profile.data.business.timezone}
            </p>
          </div>
        </div>

        <section className="mt-11 grid gap-5 lg:grid-cols-[1.45fr_0.75fr]">
          <div className="rounded-[1.75rem] border border-[#d8d2c2] bg-white p-6 sm:p-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm font-bold text-[#68776f]">Kesiapan layanan</p>
                <p className="mt-1 text-3xl font-semibold tracking-tight">
                  {health.isPending ? "Memeriksa…" : `${healthyCount}/${totalComponents} sehat`}
                </p>
              </div>
              <span
                className={`rounded-full px-4 py-2 text-sm font-bold ${
                  health.data?.status === "healthy"
                    ? "bg-[#e8f5ce] text-[#35580e]"
                    : "bg-[#fff0eb] text-[#8a321c]"
                }`}
              >
                {health.data?.status === "healthy" ? "Siap digunakan" : "Pemeriksaan berjalan"}
              </span>
            </div>

            {health.isError ? (
              <div
                className="mt-6 rounded-2xl border border-[#e8aa97] bg-[#fff3ef] p-4 text-[#8a321c]"
                role="alert"
              >
                Health API belum dapat dijangkau. Jalankan seluruh stack dan muat ulang
                halaman ini.
              </div>
            ) : (
              <div className="mt-7 grid gap-3 sm:grid-cols-2">
                {health.data
                  ? Object.entries(health.data.components).map(([name, component]) => (
                      <div
                        className="flex items-center justify-between gap-4 rounded-2xl border border-[#e2dfd6] bg-[#fbfaf7] p-4"
                        key={name}
                      >
                        <div>
                          <p className="font-semibold">{componentLabels[name] ?? name}</p>
                          <p className="mt-0.5 text-xs text-[#718078]">
                            {component.latency_ms === null
                              ? "Tidak diukur"
                              : `${component.latency_ms} ms`}
                          </p>
                        </div>
                        <HealthBadge component={component} />
                      </div>
                    ))
                  : Array.from({ length: 4 }).map((_, index) => (
                      <div
                        className="h-[78px] animate-pulse rounded-2xl bg-[#efede6]"
                        key={index}
                      />
                    ))}
              </div>
            )}
          </div>

          <aside className="rounded-[1.75rem] bg-[#153e2d] p-7 text-white sm:p-8">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#c8ef78]">
              Batas fase
            </p>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight">
              Belum ada tindakan finansial.
            </h2>
            <p className="mt-3 leading-7 text-white/65">
              Fase 0 hanya menyiapkan keamanan dan operasional. Upload, AI extraction,
              dan posting jurnal akan dimulai setelah exit gate disetujui.
            </p>
            <div className="mt-8 border-t border-white/15 pt-6">
              <p className="text-sm font-semibold">Identitas sesi</p>
              <dl className="mt-4 space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-white/55">Role</dt>
                  <dd className="capitalize">{profile.data.role}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-white/55">Currency</dt>
                  <dd>{profile.data.business.currency}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-white/55">Environment</dt>
                  <dd className="capitalize">{health.data?.environment ?? "—"}</dd>
                </div>
              </dl>
            </div>
          </aside>
        </section>

        <section className="mt-5 grid gap-5 sm:grid-cols-3">
          {[
            {
              label: "Tenant boundary",
              value: "Aktif",
              detail: "Business dan role diverifikasi dari membership database.",
            },
            {
              label: "Audit foundation",
              value: "Append-only",
              detail: "Login demo menghasilkan event dengan correlation ID.",
            },
            {
              label: "Workflow finansial",
              value: "Belum aktif",
              detail: "Menunggu persetujuan untuk memulai scope MVP 1.",
            },
          ].map((card) => (
            <article
              className="rounded-3xl border border-[#d8d2c2] bg-white p-6"
              key={card.label}
            >
              <p className="text-xs font-bold uppercase tracking-wider text-[#718078]">
                {card.label}
              </p>
              <p className="mt-3 text-2xl font-semibold">{card.value}</p>
              <p className="mt-2 text-sm leading-6 text-[#65716b]">{card.detail}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
