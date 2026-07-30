import { DocumentStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

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
      ? "bg-[#e3efe8] text-[#246449]"
      : status === "FAILED" || status === "REJECTED"
        ? "bg-[#f8e7e2] text-[#963d32]"
        : status === "READY_TO_POST"
          ? "bg-[#e4efed] text-[#376f68]"
          : "bg-[#f7efdf] text-[#805b18]";
  return (
    <Badge className={`h-6 gap-1.5 border-0 px-2.5 text-[11px] ${tone}`} variant="secondary">
      <span className="size-1 rounded-full bg-current" />
      {labels[status]}
    </Badge>
  );
}
