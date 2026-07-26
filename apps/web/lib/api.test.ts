import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, login } from "@/lib/api";

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
});
