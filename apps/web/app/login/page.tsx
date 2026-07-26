"use client";

import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { ApiError, login, sessionStorage } from "@/lib/api";

const demoAccount = {
  email: "owner@kopiarunika.demo",
  password: "Demo123!",
};

export default function LoginPage() {
  const [email, setEmail] = useState(demoAccount.email);
  const [password, setPassword] = useState(demoAccount.password);

  const loginMutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (session) => {
      sessionStorage.setToken(session.access_token);
      window.location.assign("/dashboard");
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loginMutation.mutate();
  }

  const error =
    loginMutation.error instanceof ApiError
      ? loginMutation.error.message
      : loginMutation.error
        ? "Login gagal. Pastikan API sudah berjalan, lalu coba lagi."
        : null;

  return (
    <main className="min-h-screen p-4 sm:p-7">
      <div className="mx-auto grid min-h-[calc(100vh-3.5rem)] max-w-6xl overflow-hidden rounded-[2rem] border border-[#d8d2c2] bg-white shadow-[0_30px_90px_rgba(21,62,45,0.12)] lg:grid-cols-[1.08fr_0.92fr]">
        <section className="relative hidden overflow-hidden bg-[#153e2d] p-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div
            aria-hidden="true"
            className="absolute -right-24 -top-28 h-96 w-96 rounded-full border-[64px] border-[#c8ef78]/15"
          />
          <div className="relative flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-[#c8ef78] font-black text-[#153e2d]">
              KA
            </span>
            <div>
              <p className="font-semibold tracking-tight">Kopi Arunika</p>
              <p className="text-sm text-white/60">ruang kerja demo</p>
            </div>
          </div>

          <div className="relative max-w-lg">
            <p className="mb-5 text-xs font-bold uppercase tracking-[0.22em] text-[#c8ef78]">
              Finance automation, under control
            </p>
            <h1 className="text-5xl font-semibold leading-[1.06] tracking-[-0.045em]">
              Keuangan rapi.
              <br />
              Keputusan tetap milik Anda.
            </h1>
            <p className="mt-7 max-w-md text-lg leading-8 text-white/68">
              Fondasi untuk membaca dokumen, mengawal approval, dan menunjukkan setiap
              jejak automation secara transparan.
            </p>
          </div>

          <div className="relative grid grid-cols-3 gap-3 text-sm">
            {["Tenant scoped", "Audit ready", "Mock first"].map((item, index) => (
              <div
                key={item}
                className="rounded-2xl border border-white/12 bg-white/[0.06] p-4"
              >
                <span className="mb-2 block text-[#c8ef78]">0{index + 1}</span>
                <span className="text-white/74">{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="flex items-center px-6 py-12 sm:px-12 lg:px-16">
          <div className="mx-auto w-full max-w-md">
            <div className="mb-10 lg:hidden">
              <span className="inline-grid h-11 w-11 place-items-center rounded-2xl bg-[#153e2d] font-black text-[#c8ef78]">
                KA
              </span>
            </div>

            <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#6f7f76]">
              UMKM Finance Autopilot
            </p>
            <h2 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-[#14241d]">
              Masuk ke akun demo
            </h2>
            <p className="mt-4 leading-7 text-[#637069]">
              Gunakan data sintetis Kopi Arunika. Tidak ada data atau kredensial nyata
              di environment ini.
            </p>

            <form className="mt-9 space-y-5" onSubmit={handleSubmit}>
              <div>
                <label className="mb-2 block text-sm font-semibold" htmlFor="email">
                  Email
                </label>
                <input
                  autoComplete="email"
                  className="w-full rounded-2xl border border-[#cbc8bd] bg-[#fbfaf6] px-4 py-3.5 text-[#14241d] transition hover:border-[#8a978f] focus:border-[#668b31]"
                  id="email"
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  type="email"
                  value={email}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold" htmlFor="password">
                  Password
                </label>
                <input
                  autoComplete="current-password"
                  className="w-full rounded-2xl border border-[#cbc8bd] bg-[#fbfaf6] px-4 py-3.5 text-[#14241d] transition hover:border-[#8a978f] focus:border-[#668b31]"
                  id="password"
                  minLength={8}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </div>

              {error ? (
                <div
                  className="rounded-2xl border border-[#e8aa97] bg-[#fff3ef] px-4 py-3 text-sm text-[#8a321c]"
                  role="alert"
                >
                  <strong className="block">Belum bisa masuk</strong>
                  <span>{error}</span>
                </div>
              ) : null}

              <button
                className="w-full rounded-2xl bg-[#153e2d] px-5 py-4 font-bold text-white transition hover:bg-[#20543e] disabled:cursor-wait disabled:opacity-65"
                disabled={loginMutation.isPending}
                type="submit"
              >
                {loginMutation.isPending ? "Memeriksa akses…" : "Masuk sebagai owner"}
              </button>
            </form>

            <div className="mt-6 flex items-start gap-3 rounded-2xl bg-[#f1f5e8] p-4 text-sm text-[#4f6157]">
              <span aria-hidden="true" className="mt-0.5 text-lg">
                ✓
              </span>
              <p>
                Kredensial demo sudah terisi. Login memverifikasi membership bisnis di
                server, bukan hanya isi token.
              </p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
