import type {
  DailyLogEntry,
  DailyLogStatus,
  DailyLogToday,
  Recommendation,
  Spot,
  SpotForecast,
  SpotNearby,
  SpotPreferences,
  User,
} from "./types";

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

function query(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
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

  // ── Reco ──────────────────────────────────────────────────────────────

  /** Sert l'écran d'accueil ET le comparateur : un seul aller-retour. */
  recommend: (position?: { lat: number; lon: number } | null) =>
    request<Recommendation>(
      `/recommend${position ? query({ lat: position.lat, lon: position.lon }) : ""}`,
    ),

  // ── Spots ─────────────────────────────────────────────────────────────

  spotsNearby: (params: {
    lat: number;
    lon: number;
    radius_km?: number;
    include_hidden?: boolean;
  }) => request<SpotNearby[]>(`/spots/nearby${query(params)}`),

  spot: (ref: string | number) => request<Spot>(`/spots/${ref}`),

  spotForecast: (ref: string | number, days = 5) =>
    request<SpotForecast>(`/spots/${ref}/forecast${query({ days })}`),

  createSpot: (data: {
    name: string;
    lat: number;
    lon: number;
    spot_type?: string;
  }) =>
    request<Spot>("/spots", { method: "POST", body: JSON.stringify(data) }),

  updateSpot: (ref: string | number, data: { webcam_url?: string | null }) =>
    request<Spot>(`/spots/${ref}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  setFavorite: (ref: string | number, favorite: boolean) =>
    request<SpotPreferences>(`/spots/${ref}/favorite`, {
      method: "POST",
      body: JSON.stringify({ favorite }),
    }),

  setHidden: (ref: string | number, hidden: boolean) =>
    request<SpotPreferences>(`/spots/${ref}/hide`, {
      method: "POST",
      body: JSON.stringify({ hidden }),
    }),

  preferences: () => request<SpotPreferences>("/spots/preferences"),

  updatePreferences: (data: {
    radius_km?: number;
    home_lat?: number;
    home_lon?: number;
  }) =>
    request<SpotPreferences>("/spots/preferences", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── Journal quotidien ─────────────────────────────────────────────────

  dailyLogToday: () => request<DailyLogToday>("/daily-log/today"),

  setDailyLog: (data: {
    status: DailyLogStatus;
    day?: string;
    spot_id?: number;
    reason?: string;
  }) =>
    request<DailyLogEntry>("/daily-log", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
