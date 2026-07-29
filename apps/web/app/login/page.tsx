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
    <main className="min-h-screen bg-[#f3eee5] lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(440px,0.92fr)]">
      <section className="relative hidden min-h-screen overflow-hidden border-r border-[#d7cab9] lg:block">
        <Image
          alt="Ilustrasi meja pembukuan Kopi Arunika dengan kopi, kuitansi, dan buku kas."
          className="object-cover object-top"
          fill
          priority
          sizes="55vw"
          src="/brand/coffee-ledger-login-v2.png"
        />
        <div className="absolute inset-x-0 top-0 z-10 p-10 xl:p-14">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl border border-[#d8bb88] bg-[#f8ead1]/90 shadow-[0_5px_18px_rgb(52_38_24/0.12)] backdrop-blur">
              <Image
                alt=""
                className="h-10 w-10 object-contain"
                height={40}
                priority
                src="/brand/kopi-arunika-mark.png"
                width={40}
              />
            </span>
            <div>
              <p className="text-sm font-semibold text-[#173f32]">Kopi Arunika</p>
              <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[#6f796f]">
                Finance workspace
              </p>
            </div>
          </div>
          <p className="mt-12 text-xs font-semibold uppercase tracking-[0.16em] text-[#a54f28]">
            Pembukuan yang tertelusur
          </p>
          <h1 className="mt-4 max-w-lg font-serif text-[44px] font-semibold leading-[1.04] tracking-[-0.045em] text-[#173f32] xl:text-[50px]">
            Dari dokumen harian menjadi keputusan yang jelas.
          </h1>
        </div>
      </section>

      <section className="flex min-h-screen flex-col bg-[#f3eee5]">
        <header className="flex h-[72px] items-center border-b border-[#ddd2c4] px-5 sm:px-8 lg:hidden">
          <div className="flex items-center gap-2.5">
            <span className="grid h-10 w-10 place-items-center rounded-xl border border-[#dfc28f] bg-[#f7ead3]">
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
            <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-[#777e79]">
              Finance workspace
            </p>
          </div>
          </div>
        </header>

        <div className="flex flex-1 items-center justify-center px-5 py-12 sm:px-8 lg:px-12">
          <div className="w-full max-w-md">
            <p className="eyebrow text-[#9b582f]">Akses owner</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#18251f]">
              Selamat datang kembali.
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#667169]">
              Masuk untuk meninjau dokumen dan posisi keuangan Kopi Arunika.
            </p>

            <div className="app-card mt-8 p-5 sm:p-7">
              <form className="space-y-4" onSubmit={handleSubmit}>
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

              <div className="mt-5 flex items-start gap-2.5 border-t border-[#e4dacd] pt-4 text-xs leading-5 text-[#777e79]">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#d56f3a]" />
                Kredensial demo sudah terisi. Tidak ada data atau kredensial nyata
                yang disimpan.
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
