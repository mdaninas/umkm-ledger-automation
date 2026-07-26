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
      <main className="grid min-h-screen place-items-center bg-[#f7f7f5] p-6">
        <div className="text-center" role="status">
          <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#d7dad5] border-t-[#174d3a]" />
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
    <div className="min-h-screen lg:grid lg:grid-cols-[224px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen border-r border-[#dedfdb] bg-[#f1f2ef] lg:flex lg:flex-col">
        <Link
          className="flex h-16 items-center gap-2.5 border-b border-[#dedfdb] px-4"
          href="/dashboard"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#ead9b9] bg-[#fff5e3]">
            <Image
              alt=""
              className="h-8 w-8 object-contain"
              height={32}
              priority
              src="/brand/kopi-arunika-mark.png"
              width={32}
            />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{profile.data.business.name}</p>
            <p className="text-[11px] text-[#777e79]">Finance workspace</p>
          </div>
        </Link>

        <nav className="space-y-1 p-3">
          {navigation.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return (
              <Link
                className={`flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition ${
                  active
                    ? "border border-[#d8dad5] bg-white font-semibold text-[#202522]"
                    : "font-medium text-[#666e69] hover:bg-[#e8e9e5] hover:text-[#202522]"
                }`}
                href={item.href}
                key={item.href}
              >
                <NavIcon active={active} name={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto border-t border-[#dedfdb] p-3">
          <div className="mb-3 flex items-center gap-2 px-2 text-[11px] text-[#69716c]">
            <span className="status-dot text-[#2d9169]" />
            Sistem operasional
          </div>
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#dfe5e0] text-[11px] font-semibold text-[#334139]">
              {initials}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold">
                {profile.data.user.display_name}
              </p>
              <p className="text-[10px] capitalize text-[#777e79]">{profile.data.role}</p>
            </div>
            <button
              aria-label="Keluar"
              className="grid h-8 w-8 place-items-center rounded-md text-[#747b76] hover:bg-[#e3e5e1] hover:text-[#202522]"
              onClick={logout}
              type="button"
            >
              <LogoutIcon />
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-[#dedfdb] bg-[#f7f7f5]/95 backdrop-blur lg:hidden">
          <div className="flex h-14 items-center justify-between px-4">
            <Link className="flex items-center gap-2.5" href="/dashboard">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#ead9b9] bg-[#fff5e3]">
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
              className="text-xs font-medium text-[#69716c]"
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
                      ? "border-[#174d3a] text-[#174d3a]"
                      : "border-transparent text-[#69716c]"
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
