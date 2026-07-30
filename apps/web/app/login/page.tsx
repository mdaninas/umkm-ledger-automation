"use client";

import { useMutation } from "@tanstack/react-query";
import { LoaderCircle, LockKeyhole, ShieldCheck } from "lucide-react";
import Image from "next/image";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
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
    <main className="min-h-screen bg-background lg:grid lg:grid-cols-[minmax(0,1.06fr)_minmax(440px,0.94fr)]">
      <section className="relative hidden min-h-screen overflow-hidden border-r lg:block">
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
            <span className="grid size-11 place-items-center rounded-xl border border-[#d8bb88] bg-[#f8ead1]/90 shadow-[0_5px_18px_rgb(52_38_24/0.12)] backdrop-blur">
              <Image
                alt=""
                className="size-10 object-contain"
                height={40}
                priority
                src="/brand/kopi-arunika-mark.png"
                width={40}
              />
            </span>
            <div>
              <p className="text-sm font-semibold text-[#173f32]">Kopi Arunika</p>
              <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[#657269]">
                Finance workspace
              </p>
            </div>
          </div>
          <p className="mt-12 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#a54f28]">
            Pembukuan yang tertelusur
          </p>
          <h1 className="mt-4 max-w-lg font-serif text-[44px] font-semibold leading-[1.04] tracking-[-0.045em] text-[#173f32] xl:text-[50px]">
            Dari dokumen harian menjadi keputusan yang jelas.
          </h1>
        </div>
      </section>

      <section className="flex min-h-screen flex-col">
        <header className="flex h-[72px] items-center border-b bg-card px-5 sm:px-8 lg:hidden">
          <div className="flex items-center gap-2.5">
            <span className="grid size-10 place-items-center rounded-xl border border-[#dfc28f] bg-[#f7ead3]">
              <Image
                alt=""
                className="size-9 object-contain"
                height={36}
                priority
                src="/brand/kopi-arunika-mark.png"
                width={36}
              />
            </span>
            <div>
              <p className="text-sm font-semibold">Kopi Arunika</p>
              <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                Finance workspace
              </p>
            </div>
          </div>
        </header>

        <div className="flex flex-1 items-center justify-center px-5 py-12 sm:px-8 lg:px-12">
          <div className="w-full max-w-[430px]">
            <span className="mb-5 grid size-10 place-items-center rounded-xl border bg-card text-primary shadow-sm">
              <LockKeyhole className="size-[18px]" />
            </span>
            <p className="eyebrow">Akses owner</p>
            <h2 className="mt-3 text-[32px] font-semibold tracking-[-0.045em]">
              Selamat datang kembali
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Masuk untuk meninjau dokumen dan posisi keuangan Kopi Arunika.
            </p>

            <Card className="mt-8 gap-0 py-0 shadow-[0_18px_50px_rgb(17_36_28/0.07)] ring-border">
              <CardContent className="p-5 sm:p-7">
                <form onSubmit={handleSubmit}>
                  <FieldGroup>
                    <Field>
                      <FieldLabel htmlFor="email">Email</FieldLabel>
                      <Input
                        autoComplete="email"
                        className="h-11 bg-white"
                        id="email"
                        onChange={(event) => setEmail(event.target.value)}
                        required
                        type="email"
                        value={email}
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="password">Password</FieldLabel>
                      <Input
                        autoComplete="current-password"
                        className="h-11 bg-white"
                        id="password"
                        minLength={8}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                        type="password"
                        value={password}
                      />
                    </Field>

                    {error ? (
                      <FieldError className="rounded-lg border border-[#e6bbb4] bg-[#fbefec] px-3.5 py-3">
                        <strong className="block font-semibold">
                          Belum bisa masuk
                        </strong>
                        <span>{error}</span>
                      </FieldError>
                    ) : null}

                    <Button
                      className="mt-1 h-11 w-full"
                      disabled={loginMutation.isPending}
                      size="lg"
                      type="submit"
                    >
                      {loginMutation.isPending ? (
                        <>
                          <LoaderCircle
                            className="animate-spin"
                            data-icon="inline-start"
                          />
                          Memeriksa akses…
                        </>
                      ) : (
                        "Masuk sebagai owner"
                      )}
                    </Button>
                  </FieldGroup>
                </form>

                <FieldDescription className="mt-5 flex items-start gap-2.5 border-t pt-4 text-xs leading-5">
                  <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[#d8753f]" />
                  Kredensial demo sudah terisi. Tidak ada data atau kredensial
                  nyata yang disimpan.
                </FieldDescription>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </main>
  );
}
