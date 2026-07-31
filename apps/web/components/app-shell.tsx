"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  FileStack,
  Landmark,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  ReceiptText,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useSyncExternalStore } from "react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { getProfile, sessionStorage } from "@/lib/api";
import { cn } from "@/lib/utils";

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

type NavigationItem = {
  href: string;
  label: string;
  mobileLabel: string;
  icon: LucideIcon;
};

const navigation: NavigationItem[] = [
  {
    href: "/dashboard",
    label: "Laporan",
    mobileLabel: "Laporan",
    icon: LayoutDashboard,
  },
  {
    href: "/inbox",
    label: "Dokumen",
    mobileLabel: "Dokumen",
    icon: FileStack,
  },
  {
    href: "/banking",
    label: "Mutasi bank",
    mobileLabel: "Mutasi",
    icon: Landmark,
  },
  {
    href: "/invoices",
    label: "Piutang",
    mobileLabel: "Piutang",
    icon: ReceiptText,
  },
  {
    href: "/approvals",
    label: "Approval",
    mobileLabel: "Approval",
    icon: ShieldCheck,
  },
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
      <main className="grid min-h-screen place-items-center bg-background p-6">
        <div className="text-center" role="status">
          <span className="mx-auto grid size-10 place-items-center rounded-xl border bg-card shadow-sm">
            <LoaderCircle className="size-5 animate-spin text-primary" />
          </span>
          <p className="mt-3 text-sm font-medium">Menyiapkan ruang kerja…</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Memuat data keuangan terbaru
          </p>
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
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground lg:flex lg:flex-col">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-52 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.08),transparent_65%)]" />

        <Link
          className="relative flex h-[78px] items-center gap-3 border-b border-sidebar-border px-5"
          href="/dashboard"
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-[#dfc28f] bg-[#f7ead3] shadow-[0_4px_14px_rgb(4_26_19/0.2)]">
            <Image
              alt=""
              className="size-9 object-contain"
              height={36}
              priority
              src="/brand/kopi-arunika-mark.png"
              width={36}
            />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-[-0.01em]">
              {profile.data.business.name}
            </p>
            <p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.14em] text-sidebar-foreground/55">
              Finance workspace
            </p>
          </div>
        </Link>

        <div className="relative px-4 pb-2 pt-6 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-foreground/40">
          Operasional
        </div>
        <nav className="relative space-y-1 px-3">
          {navigation.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            const Icon = item.icon;

            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                  active
                    ? "bg-white/11 text-white shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]"
                    : "text-sidebar-foreground/66 hover:bg-sidebar-accent hover:text-white",
                )}
                href={item.href}
                key={item.href}
              >
                <span
                  className={cn(
                    "absolute left-0 h-5 w-0.5 rounded-full bg-[#e3834e] opacity-0 transition-opacity",
                    active && "opacity-100",
                  )}
                />
                <Icon
                  className={cn(
                    "size-[17px] shrink-0 transition-colors",
                    active
                      ? "text-[#f0a16f]"
                      : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/85",
                  )}
                  strokeWidth={1.8}
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="relative mt-auto border-t border-sidebar-border p-3">
          <div className="mb-2 flex items-center gap-2 px-2 py-1.5 text-[11px] text-sidebar-foreground/55">
            <Activity className="size-3.5 text-[#ef9460]" />
            Sistem operasional
          </div>
          <div className="flex items-center gap-2.5 rounded-xl border border-white/[0.06] bg-black/10 p-2">
            <Avatar className="size-9 border border-white/10">
              <AvatarFallback className="bg-[#ead8bc] text-[11px] font-semibold text-[#173f32]">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold">
                {profile.data.user.display_name}
              </p>
              <p className="mt-0.5 text-[10px] capitalize text-sidebar-foreground/45">
                {profile.data.role}
              </p>
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  aria-label="Keluar"
                  className="text-sidebar-foreground/55 hover:bg-white/10 hover:text-white"
                  onClick={logout}
                  size="icon"
                  type="button"
                  variant="ghost"
                >
                  <LogOut />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Keluar</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur lg:hidden">
          <div className="flex h-14 items-center justify-between px-4">
            <Link className="flex min-w-0 items-center gap-2.5" href="/dashboard">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-[#dfc28f] bg-[#f7ead3]">
                <Image
                  alt=""
                  className="size-8 object-contain"
                  height={32}
                  priority
                  src="/brand/kopi-arunika-mark.png"
                  width={32}
                />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  {profile.data.business.name}
                </p>
                <p className="text-[9px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                  Finance workspace
                </p>
              </div>
            </Link>
            <Button
              aria-label="Keluar"
              onClick={logout}
              size="icon"
              type="button"
              variant="ghost"
            >
              <LogOut />
            </Button>
          </div>
          <nav className="grid grid-cols-5 px-1">
            {navigation.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/dashboard" && pathname.startsWith(item.href));
              const Icon = item.icon;

              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex min-w-0 flex-col items-center gap-1 px-1 py-2 text-[10px] font-medium transition-colors",
                    active ? "text-primary" : "text-muted-foreground",
                  )}
                  href={item.href}
                  key={item.href}
                >
                  <Icon className="size-4" strokeWidth={active ? 2.1 : 1.8} />
                  <span className="truncate">{item.mobileLabel}</span>
                  <span
                    className={cn(
                      "absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-[#d8753f] opacity-0",
                      active && "opacity-100",
                    )}
                  />
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
