export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export type Role = "owner" | "staff";

export interface UserSummary {
  id: string;
  email: string;
  display_name: string;
}

export interface BusinessSummary {
  id: string;
  name: string;
  timezone: string;
  currency: string;
}

export interface SessionProfile {
  user: UserSummary;
  business: BusinessSummary;
  role: Role;
}

export interface LoginResponse extends SessionProfile {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface HealthComponent {
  status: "healthy" | "unhealthy" | "skipped";
  latency_ms: number | null;
  detail: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded";
  service: string;
  environment: string;
  timestamp: string;
  components: Record<string, HealthComponent>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(
      body?.detail ?? "Layanan tidak merespons dengan benar. Silakan coba lagi.",
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getProfile(token: string): Promise<SessionProfile> {
  return apiRequest<SessionProfile>("/api/v1/auth/me", {}, token);
}

export function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/v1/health");
}

export const sessionStorage = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem("umkm_access_token");
  },
  setToken(token: string): void {
    window.localStorage.setItem("umkm_access_token", token);
  },
  clear(): void {
    window.localStorage.removeItem("umkm_access_token");
  },
};
