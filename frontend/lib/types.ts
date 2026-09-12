export type Discipline = "surf" | "foil" | "longboard";

export interface Profile {
  display_name: string | null;
  height_m: number | null;
  weight_kg: number | null;
  level: string | null;
  disciplines: Discipline[];
  timezone: string;
  /** Le spot favori : la seule prévision affichée par défaut, sur Jour. */
  home_spot_id: number | null;
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
  is_home: boolean;
}

/** Résultat du sélecteur de spot de l'écran Mer. Aucune prévision : chercher
 *  un spot n'ingère rien, la prévision arrive quand on l'ouvre. */
export interface SpotHit extends Spot {
  distance_km: number | null;
  is_favorite: boolean;
  is_home: boolean;
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
  /** 0 = basse mer, 1 = pleine mer. Nul quand le marnage est négligeable. */
  tide_position: number | null;
  tide_rising: boolean | null;
  tide_range_m: number | null;
  /** Composante offshore signée, en nœuds. Positive = vent de terre. */
  wind_offshore_kt: number | null;
  score: number | null;
  score_level: number | null;
  reasons: string[];
  /** Faux la nuit : la cellule s'éteint, elle ne disparaît pas. */
  daylight: boolean;
}

export interface SpotForecast {
  spot: Spot;
  /** Open-Meteo a dépassé les 5 s : la réponse vient de la base. */
  refreshing: boolean;
  fetched_at: string | null;
  /** Heure d'émission du run servi — « prévision de 6 h ». */
  run_ts: string | null;
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
  /** Marnage du jour, en mètres. */
  tide_range_m: number | null;
  water_temperature_c: number | null;
  /** Composante offshore signée, en nœuds. Positive = vent de terre. */
  wind_offshore_kt: number | null;
  line: string;
  /** Faux la nuit. Rendu quand même, éteint, jamais proposé. */
  daylight: boolean;
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
  position_source: "device" | "home" | "spot" | "unknown";
  verdict: Verdict;
  sentence: string;
  headline: Slot | null;
  headline_spot: Spot | null;
  /** Le favori du profil. `null` = aucun choisi, l'écran Jour le dit. */
  home_spot: Spot | null;
  /** Heure d'émission de la prévision servie — « prévision de 6 h ». */
  run_ts: string | null;
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
