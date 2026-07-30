import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { Geist } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
});

export const metadata: Metadata = {
  title: {
    default: "UMKM Finance Autopilot",
    template: "%s · UMKM Finance Autopilot",
  },
  description:
    "Automation keuangan yang terlihat, terkontrol, dan dapat diaudit untuk UMKM.",
  icons: {
    icon: "/brand/kopi-arunika-mark.png",
    apple: "/brand/kopi-arunika-mark.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html className={geist.variable} lang="id">
      <body>
        <TooltipProvider>
          <QueryProvider>{children}</QueryProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
