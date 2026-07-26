import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";

export const metadata: Metadata = {
  title: {
    default: "UMKM Finance Autopilot",
    template: "%s · UMKM Finance Autopilot",
  },
  description:
    "Automation keuangan yang terlihat, terkontrol, dan dapat diaudit untuk UMKM.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
