import type { User } from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

/** `/health` vit à la racine du back, pas sous /api/v1 (sonde Railway). */
const API_ORIGIN = API_URL.replace(/\/api\/v1\/?$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      // Le jeton vit dans un cookie httpOnly : le front ne le manipule jamais.
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch {
    // Réseau absent — cas normal sur le parking de la plage, pas une erreur
    // de programmation. L'appelant décide quoi afficher.
    throw new ApiError(0, "Réseau indisponible");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      body && typeof body.detail === "string"
        ? body.detail
        : "Une erreur est survenue";
    throw new ApiError(response.status, detail);
  }

  return body as T;
}

export const api = {
  health: () =>
    fetch(`${API_ORIGIN}/health`).then(
      (r) => r.json() as Promise<{ status: string }>,
    ),

  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>("/auth/logout", { method: "POST" }),

  me: () => request<User>("/auth/me"),
};
