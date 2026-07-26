import { DocumentStatus } from "@/lib/api";

const labels: Record<DocumentStatus, string> = {
  UPLOADED: "Diterima",
  QUEUED: "Dalam antrean",
  EXTRACTING: "Membaca dokumen",
  VALIDATING: "Memvalidasi",
  NEEDS_REVIEW: "Perlu ditinjau",
  READY_TO_POST: "Siap dibukukan",
  REJECTED: "Ditolak",
  FAILED: "Gagal",
  POSTED: "Sudah dibukukan",
  ARCHIVED: "Diarsipkan",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const tone =
    status === "POSTED"
      ? "bg-[#e8f3ed] text-[#176846]"
      : status === "FAILED" || status === "REJECTED"
        ? "bg-[#f8eae7] text-[#963d32]"
        : status === "READY_TO_POST"
          ? "bg-[#e8f1f0] text-[#376f68]"
          : "bg-[#f8f0df] text-[#805b18]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium ${tone}`}
    >
      <span className="h-1 w-1 rounded-full bg-current" />
      {labels[status]}
    </span>
  );
}
