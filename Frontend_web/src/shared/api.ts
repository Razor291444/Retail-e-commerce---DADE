export type ApiError = Error & { status?: number; code?: string };

const config = {
  gateway: import.meta.env.VITE_API_GATEWAY_URL || "",
  restPath: import.meta.env.VITE_REST_BASE_PATH || "/api",
  graphqlPath: import.meta.env.VITE_GRAPHQL_PATH || "/graphql",
  pollingMs: Number(import.meta.env.VITE_POLLING_INTERVAL_MS || 2500),
  mockFallback: String(import.meta.env.VITE_ENABLE_MOCK_FALLBACK ?? "true") === "true",
};

const tokenKey = "remarket.access_token";
const refreshTokenKey = "remarket.refresh_token";
export const apiConfig = config;

function url(path: string): string {
  return `${config.gateway}${path}`;
}

function uuid(): string {
  return crypto.randomUUID();
}

function token(): string | null {
  return sessionStorage.getItem(tokenKey);
}

export function saveAccessToken(value: string): void {
  sessionStorage.setItem(tokenKey, value);
}

export function saveRefreshToken(value: string): void {
  sessionStorage.setItem(refreshTokenKey, value);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(tokenKey);
  sessionStorage.removeItem(refreshTokenKey);
}

async function performRequest<T>(path: string, init: RequestInit, retrying = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  headers.set("X-Request-ID", uuid());
  const accessToken = token();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (["POST", "PUT", "PATCH"].includes(init.method || "GET") && path.includes("/orders")) {
    headers.set("Idempotency-Key", sessionStorage.getItem("remarket.order_key") || uuid());
    sessionStorage.setItem("remarket.order_key", headers.get("Idempotency-Key")!);
  }
  if (["POST", "PUT", "PATCH"].includes(init.method || "GET") && path.includes("/payments")) {
    headers.set("Idempotency-Key", sessionStorage.getItem("remarket.payment_key") || uuid());
    sessionStorage.setItem("remarket.payment_key", headers.get("Idempotency-Key")!);
  }
  const response = await fetch(url(path), { ...init, headers });
  if (response.status === 401 && !retrying && sessionStorage.getItem(refreshTokenKey)) {
    const refreshed = await fetch(url(`${config.restPath}/auth/refresh`), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Request-ID": uuid() },
      body: JSON.stringify({ refresh_token: sessionStorage.getItem(refreshTokenKey) }),
    });
    if (refreshed.ok) {
      const payload = await refreshed.json() as { access_token?: string; refresh_token?: string };
      if (payload.access_token) saveAccessToken(payload.access_token);
      if (payload.refresh_token) saveRefreshToken(payload.refresh_token);
      return performRequest<T>(path, init, true);
    }
  }
  if (!response.ok) {
    const error = new Error(await response.text().catch(() => response.statusText)) as ApiError;
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return performRequest<T>(path, init);
}
export async function rest<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(`${config.restPath}${path}`, init);
}

export async function graphql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const result = await request<{ data?: T; errors?: Array<{ message: string }> }>(config.graphqlPath, {
    method: "POST",
    body: JSON.stringify({ query, variables }),
  });
  if (result.errors?.length) throw new Error(result.errors.map((error) => error.message).join(", "));
  return result.data as T;
}

export async function track(event: "PAGE_VIEW" | "QR_SCAN" | "CART_ADD" | "CHECKOUT_START", data: Record<string, unknown> = {}): Promise<void> {
  const endpoint = import.meta.env.VITE_CLICKSTREAM_ENDPOINT;
  if (!endpoint) return;
  await request(endpoint, { method: "POST", body: JSON.stringify({ event, occurred_at: new Date().toISOString(), ...data }) });
}

export const demoProducts = [
  { productId: 1, barcode: "3017620422003", name: "Chocolat noir bio", category: "Épicerie", priceCents: 349, quantity: 42, nutriscore: "C" },
  { productId: 2, barcode: "3263859470008", name: "Pommes du verger local", category: "Fruits", priceCents: 299, quantity: 18, nutriscore: "A", terroirB2b: true },
  { productId: 3, barcode: "3228857000906", name: "Yaourt fermier nature", category: "Frais", priceCents: 219, quantity: 0, nutriscore: "B", terroirB2b: true },
  { productId: 4, barcode: "3760123456789", name: "Lentilles vertes", category: "Épicerie", priceCents: 489, quantity: 76, nutriscore: "A" },
];
