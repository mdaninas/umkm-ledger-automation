import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  approveInvoiceReminder,
  downloadReportCsv,
  getDashboardReport,
  login,
  runWeeklyDigest,
  runInvoiceScheduler,
  uploadBankImport,
  uploadDocument,
} from "@/lib/api";

describe("API auth client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("mengirim kredensial demo sebagai JSON", async () => {
    const responseBody = {
      access_token: "token",
      token_type: "bearer",
      expires_in: 3600,
      role: "owner",
      user: {
        id: "user-id",
        email: "owner@kopiarunika.demo",
        display_name: "Ayu Arunika",
      },
      business: {
        id: "business-id",
        name: "Kopi Arunika",
        timezone: "Asia/Jakarta",
        currency: "IDR",
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await login("owner@kopiarunika.demo", "Demo123!");

    expect(result.business.name).toBe("Kopi Arunika");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "owner@kopiarunika.demo",
          password: "Demo123!",
        }),
      }),
    );
  });

  it("menggunakan pesan aman dari API saat login ditolak", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Email atau password tidak cocok." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(login("owner@kopiarunika.demo", "WrongPass123!")).rejects.toEqual(
      new ApiError("Email atau password tidak cocok.", 401),
    );
  });

  it("mengunggah dokumen sebagai multipart tanpa mengatur content type manual", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "document-id",
          original_filename: "receipt.pdf",
          status: "QUEUED",
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "upload-request-0001" });

    await uploadDocument(
      "access-token",
      new File(["%PDF-1.4"], "receipt.pdf", { type: "application/pdf" }),
    );

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.body).toBeInstanceOf(FormData);
    const headers = options.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer access-token");
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.get("Idempotency-Key")).toBe("upload-request-0001");
  });

  it("mengirim file mutasi dan mapping kolom sebagai multipart", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "bank-import-id",
          filename: "mutasi.csv",
          status: "COMPLETED",
          row_count: 1,
          imported_count: 1,
          duplicate_count: 0,
          error_count: 0,
          row_errors: [],
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(
      ["tanggal,deskripsi,debit,kredit\n2026-07-25,Biji kopi,350000,\n"],
      "mutasi.csv",
      { type: "text/csv" },
    );

    await uploadBankImport("access-token", file, {
      date: "tanggal",
      description: "deskripsi",
      debit: "debit",
      credit: "kredit",
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const body = options.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("mapping")).toBe(
      JSON.stringify({
        date: "tanggal",
        description: "deskripsi",
        debit: "debit",
        credit: "kredit",
      }),
    );
    const headers = options.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("menjalankan clock invoice dan mengirim approval idempotent", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            as_of: "2026-07-31",
            businesses_scanned: 1,
            invoices_scanned: 3,
            status_updates: 2,
            drafts_created: 1,
            fallback_drafts: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "invoice-id",
            reminders: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await runInvoiceScheduler("access-token", "2026-07-31");
    await approveInvoiceReminder(
      "access-token",
      "reminder-id",
      "Data penerima sudah benar.",
    );

    const schedulerOptions = fetchMock.mock.calls[0][1] as RequestInit;
    expect(schedulerOptions.body).toBe(
      JSON.stringify({ as_of: "2026-07-31", force_fallback: false }),
    );
    const approvalOptions = fetchMock.mock.calls[1][1] as RequestInit;
    const approvalHeaders = approvalOptions.headers as Headers;
    expect(approvalHeaders.get("Idempotency-Key")).toBe(
      "approve-reminder-reminder-id",
    );
  });

  it("memakai periode yang sama untuk dashboard, digest, dan ekspor CSV", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            period: {
              start_date: "2026-07-01",
              end_date: "2026-07-31",
            },
            overview: { available_cash: "45450000.00" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "digest-id",
            period_end: "2026-07-31",
            narrative: "Ringkasan berbasis ledger.",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response("tanggal,journal_id\n", {
          status: 200,
          headers: {
            "Content-Type": "text/csv",
            "Content-Disposition":
              'attachment; filename="laporan-2026-07-01-2026-07-31.csv"',
          },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await getDashboardReport("access-token", "2026-07-01", "2026-07-31");
    await runWeeklyDigest("access-token", "2026-07-31");
    const exported = await downloadReportCsv(
      "access-token",
      "2026-07-01",
      "2026-07-31",
    );

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/v1/reports/dashboard?start_date=2026-07-01&end_date=2026-07-31",
    );
    const digestOptions = fetchMock.mock.calls[1][1] as RequestInit;
    expect(digestOptions.body).toBe(
      JSON.stringify({ period_end: "2026-07-31" }),
    );
    expect(fetchMock.mock.calls[2][0]).toContain(
      "/api/v1/reports/export.csv?start_date=2026-07-01&end_date=2026-07-31",
    );
    expect(exported.filename).toBe("laporan-2026-07-01-2026-07-31.csv");
  });
});
