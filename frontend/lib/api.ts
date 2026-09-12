import type {
  ApiToken,
  ApiTokenCreated,
  DailyLogEntry,
  DailyLogStatus,
  DailyLogToday,
  Discipline,
  GearType,
  GearWithUsage,
  Recommendation,
  SessionJournal,
  SessionStatus,
  Spot,
  SpotForecast,
  SpotHit,
  SpotNearby,
  SpotPreferences,
  SurfSession,
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

/** Le corps d'une notation. Partagé avec la file hors ligne, qui rejoue
 *  exactement cette forme au retour du réseau. */
export interface SessionUpdate {
  spot_id?: number;
  started_at?: string;
  duration_min?: number;
  rating_conditions?: number;
  rating_personal?: number;
  gear_id?: number;
  wave_count?: number;
  notes?: string | null;
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

  /** Le spot favori passe par là : c'est lui qui décide de ce qui est ingéré
   *  en planifié, et de la prévision affichée sur Jour. */
  updateProfile: (data: { home_spot_id?: number; timezone?: string }) =>
    request<User>("/auth/me/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

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

  /** `step_hours: 3` sert la grille 5 jours × 8 créneaux de l'écran Mer :
   *  quarante points au lieu de cent vingt, sur un réseau de parking de plage. */
  spotForecast: (ref: string | number, days = 5, stepHours = 1) =>
    request<SpotForecast>(
      `/spots/${ref}/forecast${query({ days, step_hours: stepHours })}`,
    ),

  /** Recherche par nom dans le catalogue. N'ingère rien. */
  searchSpots: (
    q: string,
    position?: { lat: number; lon: number } | null,
  ) =>
    request<SpotHit[]>(
      `/spots/search${query({ q, lat: position?.lat, lon: position?.lon })}`,
    ),

  /** Les spots maison, le favori du profil en tête. N'ingère rien non plus. */
  favoriteSpots: () => request<SpotHit[]>("/spots/favorites"),

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

  // ── Sessions ──────────────────────────────────────────────────────────

  /** Tout ce dont l'écran Jour a besoin, en un aller-retour : les sessions à
   *  noter (de n'importe quel jour) et celles d'aujourd'hui. */
  sessionJournal: () => request<SessionJournal>("/sessions/today"),

  sessions: (params: {
    status?: SessionStatus;
    since?: string;
    until?: string;
    limit?: number;
    offset?: number;
  } = {}) => request<SurfSession[]>(`/sessions${query(params)}`),

  session: (id: number) => request<SurfSession>(`/sessions/${id}`),

  /** La notation. Le passage en `rated` est décidé par le serveur, qui
   *  regarde si les **deux** notes sont là — jamais par le front. */
  updateSession: (id: number, data: SessionUpdate) =>
    request<SurfSession>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  createSession: (data: {
    spot_id: number;
    started_at: string;
    duration_min?: number;
    discipline?: Discipline;
    rating_conditions?: number;
    rating_personal?: number;
    gear_id?: number;
    wave_count?: number;
    notes?: string;
    client_uuid?: string;
  }) =>
    request<SurfSession>("/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteSession: (id: number) =>
    request<void>(`/sessions/${id}`, { method: "DELETE" }),

  /** Photo de session — multipart, donc hors du `request` JSON.
   *  Exige le réseau : une photo ne va pas dans la file hors ligne, qui est
   *  faite pour des notes de quelques octets. */
  uploadSessionPhoto: async (id: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    let response: Response;
    try {
      response = await fetch(`${API_URL}/sessions/${id}/photo`, {
        method: "POST",
        credentials: "include",
        body,
      });
    } catch {
      throw new ApiError(0, "Réseau indisponible");
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(
        response.status,
        typeof payload?.detail === "string"
          ? payload.detail
          : "Photo non enregistrée",
      );
    }
    return payload as SurfSession;
  },

  // ── Matos ─────────────────────────────────────────────────────────────

  gear: (includeInactive = true) =>
    request<GearWithUsage[]>(`/gear${query({ include_inactive: includeInactive })}`),

  createGear: (data: {
    name: string;
    gear_type?: GearType;
    length_m?: number | null;
    volume_l?: number | null;
    discipline?: Discipline;
    purchased_on?: string | null;
  }) => request<GearWithUsage>("/gear", { method: "POST", body: JSON.stringify(data) }),

  updateGear: (
    id: number,
    data: {
      name?: string;
      length_m?: number | null;
      volume_l?: number | null;
      is_active?: boolean;
    },
  ) =>
    request<GearWithUsage>(`/gear/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteGear: (id: number) =>
    request<void>(`/gear/${id}`, { method: "DELETE" }),

  // ── Jetons d'API (raccourci iPhone) ───────────────────────────────────

  tokens: () => request<ApiToken[]>("/auth/tokens"),

  /** La valeur du jeton n'est renvoyée qu'ici, une seule fois. */
  createToken: (name: string) =>
    request<ApiTokenCreated>("/auth/tokens", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  revokeToken: (id: number) =>
    request<void>(`/auth/tokens/${id}`, { method: "DELETE" }),

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
