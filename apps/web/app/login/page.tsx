"use client";

import { useMutation } from "@tanstack/react-query";
import Image from "next/image";
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
    <main className="min-h-screen bg-[#f7f7f5]">
      <header className="flex h-16 items-center border-b border-[#dedfdb] px-5 sm:px-8">
        <div className="flex items-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-lg border border-[#ead9b9] bg-[#fff5e3]">
            <Image
              alt=""
              className="h-9 w-9 object-contain"
              height={36}
              priority
              src="/brand/kopi-arunika-mark.png"
              width={36}
            />
          </span>
          <div>
            <p className="text-sm font-semibold">Kopi Arunika</p>
            <p className="text-[11px] text-[#777e79]">Finance workspace</p>
          </div>
        </div>
      </header>

      <section className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center px-5 py-12 sm:px-8 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-24">
        <div className="hidden lg:block">
          <p className="text-sm font-medium text-[#174d3a]">Ruang kerja demo</p>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold leading-[1.15] tracking-[-0.045em] text-[#202522]">
            Dokumen masuk, pembukuan tertelusur.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-[#69716c]">
            Tinjau hasil ekstraksi, koreksi akun, lalu posting jurnal dengan jejak
            keputusan yang lengkap.
          </p>
          <dl className="mt-10 max-w-lg divide-y divide-[#dedfdb] border-y border-[#dedfdb]">
            <Feature label="Dokumen privat" value="Akses berbasis workspace" />
            <Feature label="Review owner" value="Tidak ada posting tanpa konfirmasi" />
            <Feature label="Audit trail" value="Setiap perubahan tercatat" />
          </dl>
        </div>

        <div className="app-card w-full p-6 sm:p-8">
          <p className="text-xs font-medium text-[#69716c]">UMKM Finance Autopilot</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
            Masuk ke akun demo
          </h2>
          <p className="mt-2 text-sm leading-6 text-[#69716c]">
            Kredensial sintetis sudah terisi untuk Kopi Arunika.
          </p>

          <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="mb-1.5 block text-xs font-medium" htmlFor="email">
                Email
              </label>
              <input
                autoComplete="email"
                className="form-control"
                id="email"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium" htmlFor="password">
                Password
              </label>
              <input
                autoComplete="current-password"
                className="form-control"
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
                className="rounded-lg border border-[#e3b7af] bg-[#fbeeea] px-3.5 py-3 text-sm text-[#8d3a30]"
                role="alert"
              >
                <strong className="block font-semibold">Belum bisa masuk</strong>
                <span>{error}</span>
              </div>
            ) : null}

            <button
              className="primary-button !mt-6 w-full"
              disabled={loginMutation.isPending}
              type="submit"
            >
              {loginMutation.isPending ? "Memeriksa akses…" : "Masuk sebagai owner"}
            </button>
          </form>

          <p className="mt-5 border-t border-[#e3e4e1] pt-4 text-xs leading-5 text-[#777e79]">
            Environment ini tidak menyimpan data atau kredensial nyata.
          </p>
        </div>
      </section>
    </main>
  );
}

function Feature({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[150px_minmax(0,1fr)] gap-6 py-4 text-sm">
      <dt className="font-medium">{label}</dt>
      <dd className="text-[#69716c]">{value}</dd>
    </div>
  );
}
