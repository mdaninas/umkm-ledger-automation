"use client";

import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useSyncExternalStore } from "react";
import { getProfile, sessionStorage } from "@/lib/api";

const subscribeToSession = (onStoreChange: () => void) => {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener("umkm-session", onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener("umkm-session", onStoreChange);
  };
};

export function useSessionToken(): string | null {
  return useSyncExternalStore(
    subscribeToSession,
    sessionStorage.getToken,
    () => null,
  );
}

const navigation = [
  { href: "/dashboard", label: "Ringkasan", icon: "dashboard" },
  { href: "/inbox", label: "Dokumen", icon: "inbox" },
  { href: "/banking", label: "Mutasi bank", icon: "bank" },
  { href: "/approvals", label: "Approval", icon: "approval" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const token = useSessionToken();
  const profile = useQuery({
    queryKey: ["session-profile"],
    queryFn: () => getProfile(token!),
    enabled: Boolean(token),
    retry: false,
  });

  useEffect(() => {
    if (profile.isError) {
      sessionStorage.clear();
      router.replace("/login");
    } else if (!token && !sessionStorage.getToken()) {
      router.replace("/login");
    }
  }, [profile.isError, router, token]);

  if (!token || profile.isPending || !profile.data) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3eee5] p-6">
        <div className="text-center" role="status">
          <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#d8cec0] border-t-[#173f32]" />
          <p className="mt-3 text-sm font-medium">Menyiapkan ruang kerja…</p>
        </div>
      </main>
    );
  }

  function logout() {
    sessionStorage.clear();
    router.replace("/login");
  }

  const initials = profile.data.user.display_name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("");

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[244px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen overflow-hidden border-r border-[#2b5143] bg-[#143a2f] text-[#f8f1e5] lg:flex lg:flex-col">
        <Link
          className="flex h-[72px] items-center gap-3 border-b border-[#315447] px-4"
          href="/dashboard"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[#dfc28f] bg-[#f7ead3] shadow-[0_4px_12px_rgb(5_23_18/0.18)]">
            <Image
              alt=""
              className="h-9 w-9 object-contain"
              height={36}
              priority
              src="/brand/kopi-arunika-mark.png"
              width={36}
            />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{profile.data.business.name}</p>
            <p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.13em] text-[#a9beb5]">
              Finance workspace
            </p>
          </div>
        </Link>

        <div className="px-5 pb-2 pt-6 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7fa093]">
          Workspace
        </div>
        <nav className="space-y-1 px-3">
          {navigation.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return (
              <Link
                className={`relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm transition ${
                  active
                    ? "bg-[#f4eadb] font-semibold text-[#173f32] shadow-[0_3px_10px_rgb(6_26_20/0.12)]"
                    : "font-medium text-[#bed0c8] hover:bg-[#20483a] hover:text-white"
                }`}
                href={item.href}
                key={item.href}
              >
                {active ? (
                  <span className="absolute -left-0.5 h-5 w-1 rounded-full bg-[#d56f3a]" />
                ) : null}
                <NavIcon active={active} name={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto border-t border-[#315447] p-3">
          <div className="mb-2 flex items-center gap-2 px-2 py-1 text-[11px] text-[#9cb5aa]">
            <span className="status-dot text-[#e28a53]" />
            Sistem operasional
          </div>
          <div className="flex items-center gap-2.5 rounded-xl bg-[#103328] px-2 py-2.5">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#e9d7bd] text-[11px] font-semibold text-[#173f32]">
              {initials}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold">
                {profile.data.user.display_name}
              </p>
              <p className="text-[10px] capitalize text-[#8eaa9e]">{profile.data.role}</p>
            </div>
            <button
              aria-label="Keluar"
              className="grid h-8 w-8 place-items-center rounded-md text-[#96aea4] hover:bg-[#244c3e] hover:text-white"
              onClick={logout}
              type="button"
            >
              <LogoutIcon />
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-[#d9cebf] bg-[#f3eee5]/95 backdrop-blur lg:hidden">
          <div className="flex h-14 items-center justify-between px-4">
            <Link className="flex items-center gap-2.5" href="/dashboard">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-[#dfc28f] bg-[#f7ead3]">
                <Image
                  alt=""
                  className="h-8 w-8 object-contain"
                  height={32}
                  priority
                  src="/brand/kopi-arunika-mark.png"
                  width={32}
                />
              </span>
              <p className="max-w-44 truncate text-sm font-semibold">
                {profile.data.business.name}
              </p>
            </Link>
            <button
              className="text-xs font-medium text-[#667169]"
              onClick={logout}
              type="button"
            >
              Keluar
            </button>
          </div>
          <nav className="flex overflow-x-auto px-2">
            {navigation.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/dashboard" && pathname.startsWith(item.href));
              return (
                <Link
                  className={`border-b-2 px-3 py-2 text-xs font-medium ${
                    active
                      ? "border-[#d56f3a] text-[#173f32]"
                      : "border-transparent text-[#667169]"
                  }`}
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>
        {children}
      </div>
    </div>
  );
}

function NavIcon({ name, active }: { name: string; active: boolean }) {
  const stroke = active ? "#174d3a" : "currentColor";
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
    >
      {name === "dashboard" ? (
        <>
          <rect height="7" rx="1.5" stroke={stroke} strokeWidth="1.7" width="7" x="3" y="3" />
          <rect height="7" rx="1.5" stroke={stroke} strokeWidth="1.7" width="7" x="14" y="3" />
          <rect height="7" rx="1.5" stroke={stroke} strokeWidth="1.7" width="7" x="3" y="14" />
          <rect height="7" rx="1.5" stroke={stroke} strokeWidth="1.7" width="7" x="14" y="14" />
        </>
      ) : name === "inbox" ? (
        <>
          <path d="M4 4h16v16H4z" stroke={stroke} strokeLinejoin="round" strokeWidth="1.7" />
          <path d="M4 14h4l2 3h4l2-3h4" stroke={stroke} strokeLinejoin="round" strokeWidth="1.7" />
        </>
      ) : name === "bank" ? (
        <>
          <path d="m3 9 9-5 9 5" stroke={stroke} strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
          <path d="M5 10h14M6 10v7m4-7v7m4-7v7m4-7v7M4 20h16" stroke={stroke} strokeLinecap="round" strokeWidth="1.7" />
        </>
      ) : (
        <>
          <path d="M12 3 5 6v5c0 4.6 2.9 8.7 7 10 4.1-1.3 7-5.4 7-10V6l-7-3Z" stroke={stroke} strokeLinejoin="round" strokeWidth="1.7" />
          <path d="m9 12 2 2 4-4" stroke={stroke} strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
        </>
      )}
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 24 24" width="16">
      <path d="M14 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2v-3" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      <path d="m10 12 3-3m-3 3 3 3m-3-3h11" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}
