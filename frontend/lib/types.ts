export type Discipline = "surf" | "foil" | "longboard";

export interface Profile {
  display_name: string | null;
  height_m: number | null;
  weight_kg: number | null;
  level: string | null;
  disciplines: Discipline[];
  timezone: string;
}

export interface User {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
  profile: Profile | null;
}

// ── Spots ────────────────────────────────────────────────────────────────

export type SpotSource = "osm" | "user";
export type SpotType = "beach" | "reef" | "point" | "unknown";
/** Niveau d'ingestion : `home` planifié, `potential` à la demande, `catalog` jamais. */
export type SpotTier = "home" | "potential" | "catalog";

export interface Spot {
  id: number;
  slug: string;
  name: string;
  lat: number;
  lon: number;
  country_code: string | null;
  region: string | null;
  spot_type: SpotType;
  source: SpotSource;
  /** Calculée depuis le trait de côte OSM, jamais saisie. */
  coast_bearing_deg: number | null;
  /** Direction d'où vient un vent onshore. */
  onshore_dir_deg: number | null;
  webcam_url: string | null;
  tier: SpotTier;
}

export interface SpotNearby extends Spot {
  distance_km: number;
  is_favorite: boolean;
  is_hidden: boolean;
}

export interface SpotPreferences {
  radius_km: number;
  home_lat: number | null;
  home_lon: number | null;
  favorite_spot_ids: number[];
  hidden_spot_ids: number[];
  last_lat: number | null;
  last_lon: number | null;
  last_position_at: string | null;
}

// ── Prévisions et notes ──────────────────────────────────────────────────

/** Unités de base : mètres, secondes, degrés, nœuds. */
export interface ForecastPoint {
  ts: string;
  wave_height_m: number | null;
  wave_direction_deg: number | null;
  wave_period_s: number | null;
  wave_peak_period_s: number | null;
  swell_height_m: number | null;
  swell_direction_deg: number | null;
  swell_period_s: number | null;
  wind_speed_kt: number | null;
  wind_gust_kt: number | null;
  wind_direction_deg: number | null;
  sea_level_m: number | null;
  water_temperature_c: number | null;
  score: number | null;
  score_level: number | null;
}

export interface SpotForecast {
  spot: Spot;
  /** Open-Meteo a dépassé les 5 s : la réponse vient de la base. */
  refreshing: boolean;
  fetched_at: string | null;
  points: ForecastPoint[];
}

export type Verdict = "OUI" | "NON" | "PEUT-ÊTRE";

export interface Slot {
  ts: string;
  score: number;
  /** 1 à 5 — c'est ce niveau qui choisit la couleur de la cellule. */
  level: number;
  verdict: Verdict;
  reasons: string[];
  wave_height_m: number | null;
  wave_period_s: number | null;
  wave_direction_deg: number | null;
  wind_speed_kt: number | null;
  wind_gust_kt: number | null;
  wind_direction_deg: number | null;
  sea_level_m: number | null;
  tide_position: number | null;
  tide_rising: boolean | null;
  water_temperature_c: number | null;
  line: string;
}

export interface SpotSlots {
  spot: Spot;
  distance_km: number | null;
  best: Slot | null;
  slots: Slot[];
}

export interface Recommendation {
  generated_at: string;
  lat: number;
  lon: number;
  position_source: "device" | "home" | "unknown";
  verdict: Verdict;
  sentence: string;
  headline: Slot | null;
  headline_spot: Spot | null;
  spots: SpotSlots[];
  refreshing: number[];
}

// ── Journal quotidien ────────────────────────────────────────────────────

export type DailyLogStatus = "surfed" | "watched_and_passed" | "not_watched";

export interface DailyLogEntry {
  id: number;
  day: string;
  status: DailyLogStatus;
  spot_id: number | null;
  reason: string | null;
  created_at: string;
}

export interface DailyLogToday {
  day: string;
  answered: boolean;
  entry: DailyLogEntry | null;
}
