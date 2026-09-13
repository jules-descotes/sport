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

/** Résultat du sélecteur de spot de l'écran Surf. Aucune prévision : chercher
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
  /** Train secondaire — features 16 et 17 du registre. Ligne repliable. */
  secondary_swell_height_m: number | null;
  secondary_swell_direction_deg: number | null;
  secondary_swell_period_s: number | null;
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
  /** Flux d'énergie de la houle en kJ/s par mètre de crête — ∝ H²·T
   *  (feature 9). Un mètre à 15 s porte trois fois l'énergie d'un mètre à 7 s,
   *  et c'est ce que la hauteur seule ne dit pas. */
  wave_energy_kj: number | null;
  /** Écart angulaire houle ↔ orientation du spot (feature 10). */
  swell_alignment_deg: number | null;
  score: number | null;
  score_level: number | null;
  reasons: string[];
  /** Faux la nuit : la cellule s'éteint, elle ne disparaît pas. */
  daylight: boolean;
}

/** Lever et coucher d'une journée, en UTC. Le tableau horaire grise la nuit
 *  d'un trait plutôt que d'éteindre chaque cellule. */
export interface SunDay {
  day: string;
  sunrise: string | null;
  sunset: string | null;
}

/** Le détail d'un créneau — le seul endroit où les directions sont chiffrées. */
export interface SlotDetail {
  point: ForecastPoint;
  spot: Spot;
  wave_direction_label: string | null;
  wind_direction_label: string | null;
  secondary_swell_direction_label: string | null;
  onshore_direction_label: string | null;
  sunrise: string | null;
  sunset: string | null;
  run_ts: string | null;
  previous_run_ts: string | null;
  /** Coefficient de la pleine mer la plus proche de ce créneau. */
  tide_coefficient: number | null;
  tide_coefficient_approximate: boolean;
  /** Écarts signés depuis le run de la veille au soir. Directions repliées
   *  par le court chemin : 350° → 10° vaut +20°. */
  delta: Record<string, number>;
}

/**
 * Une pleine mer et son coefficient — calculé à Brest, national par définition.
 *
 * `approximate` se rend par un « ≈ » devant le chiffre. Il est vrai tant que
 * l'écart mesuré contre l'annuaire SHOM dépasse cinq points
 * (`docs/COEFFICIENT-MAREE.md`), ou que la fenêtre de référence de trente jours
 * n'est pas encore remplie.
 */
export interface TideCoefficientMark {
  ts: string;
  value: number;
  approximate: boolean;
  reason: string | null;
}

export interface TideCoefficientDay {
  day: string;
  marks: TideCoefficientMark[];
}

export interface SpotForecast {
  spot: Spot;
  /** Open-Meteo a dépassé les 5 s : la réponse vient de la base. */
  refreshing: boolean;
  fetched_at: string | null;
  /** Heure d'émission du run servi — « prévision de 6 h ». */
  run_ts: string | null;
  /** Une entrée par journée rendue, dans l'ordre. */
  sun: SunDay[];
  points: ForecastPoint[];
}

/** Les huit points de la rose, tels qu'on les saisit. */
export const SECTORS_8 = [
  "N",
  "NE",
  "E",
  "SE",
  "S",
  "SO",
  "O",
  "NO",
] as const;
export type Sector8 = (typeof SECTORS_8)[number];

export const TIDE_PHASES = ["low", "rising", "high", "falling"] as const;
export type TidePhase = (typeof TIDE_PHASES)[number];

/**
 * Les critères de Jules pour un spot — larges, et tous optionnels.
 *
 * **Un champ vide n'est pas une valeur par défaut, c'est une absence de
 * contrainte.** C'est la décision qui structure tout le reste : on ne remplit
 * pas les trous avec des seuils inventés, et un spot dont on ne sait dire que
 * « pas plus de 2 m » est décrit par cette seule ligne.
 */
export interface SpotRules {
  spot_id: number;
  wave_height_min_m: number | null;
  wave_height_max_m: number | null;
  wave_period_min_s: number | null;
  swell_sectors: Sector8[];
  wind_sectors: Sector8[];
  wind_max_kt: number | null;
  tide_phases: TidePhase[];
  hour_min: number | null;
  hour_max: number | null;
  updated_at?: string | null;
}

/**
 * Une fenêtre à venir où un favori correspond à ses critères.
 *
 * « Parlementia devrait marcher — dim. 10 h à 13 h · 1,6 m / 13 s / NO · vent
 * E 6 kt · montante ». Le conditionnel vient du serveur : ce sont des critères
 * larges confrontés à une prévision, pas une promesse.
 */
export interface MatchWindow {
  spot: Spot;
  start: string;
  end: string;
  best_ts: string;
  best_score: number;
  sentence: string;
  details: string;
  wave_height_m: number | null;
  wave_period_s: number | null;
  wave_direction_deg: number | null;
  wind_speed_kt: number | null;
  wind_direction_deg: number | null;
  tide_phase: TidePhase | null;
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
  /** Les autres favoris qui devraient marcher sous trois jours. */
  matches: MatchWindow[];
  /** Vrai quand le favori principal correspond aussi à ses critères. */
  home_matches: boolean;
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

// ── Matos ────────────────────────────────────────────────────────────────

export type GearType = "board" | "wetsuit" | "accessory";

/** Longueur en **mètres** : un 6'2 est une unité composite, interdite en base
 *  (cf. CLAUDE.md). La conversion en pieds-pouces est un affichage, comme
 *  celle des heures UTC en heure locale — voir `boardLength` dans `format.ts`. */
export interface Gear {
  id: number;
  name: string;
  gear_type: GearType;
  length_m: number | null;
  volume_l: number | null;
  discipline: Discipline;
  purchased_on: string | null;
  is_active: boolean;
  created_at: string;
}

export interface GearWithUsage extends Gear {
  /** Calculé depuis les sessions, jamais stocké. */
  session_count: number;
  /** Porte la présélection de l'écran de notation. */
  last_used_at: string | null;
}

// ── Sessions ─────────────────────────────────────────────────────────────

/** `to_rate` tant que les **deux** notes ne sont pas posées. */
export type SessionStatus = "to_rate" | "rated";

/**
 * Une heure de session, notée à part (décidé le 13/09).
 *
 * `started_at` est une **heure pleine** en UTC : c'est la clé d'appariement
 * avec la ligne horaire du `conditions_snapshot`, et c'est ce qui fait du
 * segment un point d'apprentissage plutôt qu'un détail d'affichage. Le serveur
 * la recale de toute façon.
 *
 * Les notes vont de 1 à 5 par pas de 0,5, comme celles de la session. La base
 * les stocke en entiers ×2 ; le front ne voit jamais ce ×2.
 */
export interface SessionSegmentValue {
  started_at: string;
  rating_conditions: number | null;
  rating_personal: number | null;
}

export interface SurfSession {
  id: number;
  spot_id: number;
  spot: Spot | null;
  started_at: string;
  duration_min: number | null;
  discipline: Discipline;
  status: SessionStatus;
  /** De 1 à 5 **par pas de 0,5** depuis le 13/09. */
  rating_conditions: number | null;
  rating_personal: number | null;
  /** Les notes heure par heure, dans l'ordre. Vide le plus souvent : la note
   *  globale reste la référence d'affichage. */
  segments: SessionSegmentValue[];
  gear_id: number | null;
  gear: Gear | null;
  wave_count: number | null;
  crowd: number | null;
  notes: string | null;
  photo_url: string | null;
  lat: number | null;
  lon: number | null;
  client_uuid: string | null;
  /** Début deviné par le serveur (fin − 90 min) et pas encore corrigé. */
  start_estimated: boolean;
  conditions_snapshot: ConditionsSnapshot | null;
  /** Les snapshots remplacés par une correction, du plus ancien au plus
   *  récent. Jamais écrasés : c'est la seule donnée du projet qu'on ne peut
   *  pas reconstituer après coup. */
  snapshot_history: SnapshotVersion[];
  /** Non nul = en corbeille. Trente jours, puis purge. */
  deleted_at: string | null;
  created_at: string;
  /** Énergie de la houle à l'heure de la session — la colonne de l'historique.
   *  Dérivée du snapshot côté serveur : une seule constante, un seul chiffre. */
  wave_energy_kj: number | null;
}

/** Un snapshot mis de côté, avec la raison qui l'a fait refaire. */
export interface SnapshotVersion {
  replaced_at: string;
  reason: string;
  spot_id: number;
  started_at: string;
  snapshot: ConditionsSnapshot;
}

/** Ce que l'écran Jour demande en un seul aller-retour. */
export interface SessionJournal {
  to_rate: SurfSession[];
  today: SurfSession[];
}

/** Un point de la fenêtre T−2 h / T−1 h / T0. */
export interface SnapshotEntry {
  offset_h: number;
  ts: string;
  wave_height_m: number | null;
  wave_direction_deg: number | null;
  wave_period_s: number | null;
  wind_speed_kt: number | null;
  wind_gust_kt: number | null;
  wind_direction_deg: number | null;
  sea_level_m: number | null;
  water_temperature_c: number | null;
  /** Calculée à la lecture depuis H et T, jamais stockée — même constante
   *  que l'écran Surf (0,49 × H² × T, en kJ/s par mètre de crête). */
  wave_energy_kj: number | null;
}

/**
 * Figé à l'enregistrement, irrattrapable après coup (cf. CLAUDE.md, règle 7).
 * Deux volets qui ne se mélangent jamais : `forecast` (ce qui était annoncé,
 * runs émis avant le début seulement) et `observed` (ce qui s'est passé).
 */
export interface ConditionsSnapshot {
  window_hours: number[];
  reference_ts: string;
  model: string;
  model_version: string | null;
  forecast: SnapshotEntry[];
  observed: SnapshotEntry[];
  trends: {
    forecast: Record<string, number | null>;
    observed: Record<string, number | null>;
  };
  tide: {
    range_m: number | null;
    position: number | null;
    trend_m_per_h: number | null;
  };
  observed_error?: string;
}

export interface QuickSessionResponse {
  session: SurfSession;
  created: boolean;
  spot_source: "nearest" | "home" | "existing";
  spot_distance_km: number | null;
  rate_url: string;
  rate_path: string;
}

// ── Jetons d'API ─────────────────────────────────────────────────────────

export interface ApiToken {
  id: number;
  name: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** La seule réponse qui porte le jeton en clair, et elle ne revient pas. */
export interface ApiTokenCreated extends ApiToken {
  token: string;
}

// ── Training ─────────────────────────────────────────────────────────────

export interface Measurement {
  id: number;
  /** Date locale — on ne mesure pas sa souplesse à la seconde près. */
  measured_on: string;
  value: number;
  note: string | null;
}

/**
 * Une jauge : départ, aujourd'hui, cible.
 *
 * `start_value` est la **première mesure**, jamais une valeur saisie. Tant
 * qu'il n'y a aucune mesure, tout est nul et l'écran le dit — une jauge à
 * moitié pleine se lirait comme un relevé.
 */
export interface Objective {
  id: number;
  slug: string;
  name: string;
  measure: string;
  /** Unité de base : `cm`, `deg`, `s`. Le « 2:10 » est un affichage. */
  unit: string;
  /** `up` = plus c'est haut, mieux c'est. `down` = l'inverse. */
  direction: "up" | "down";
  target_value: number | null;
  start_value: number | null;
  current_value: number | null;
  /** 0 au départ, 1 sur la cible. Nul tant qu'il manque une borne. */
  ratio: number | null;
  last_measured_on: string | null;
  measure_every_days: number;
  /** Vrai quand la fréquence est dépassée, ou qu'aucune mesure n'existe. */
  needs_measurement: boolean;
  measurements: Measurement[];
}

export type ExerciseCategory = "mobility" | "strength" | "core";

export interface Exercise {
  id: number;
  slug: string;
  name: string;
  category: ExerciseCategory;
  muscle_group: string | null;
  instructions: string | null;
  image_url: string | null;
  /** Toujours renseignés : `builtin`, `wger`, `free-exercise-db`. */
  source: string;
  license: string | null;
  source_url: string | null;
}

export interface FormulaItem {
  id: number;
  position: number;
  sets: number;
  /** L'un **ou** l'autre : un gainage se tient, une rotation se compte. */
  reps: number | null;
  duration_s: number | null;
  tempo: string | null;
  rest_s: number;
  note: string | null;
  exercise: Exercise;
}

export interface Formula {
  id: number;
  slug: string;
  name: string;
  duration_min: number;
  weekly_target: number;
  /** La ligne qui justifie la formule — pas de la décoration. */
  principle: string;
  objective_slugs: string[];
  tags: string[];
  variant_of: string | null;
  family: string;
  items: FormulaItem[];
  /** Séances complètes cette semaine, comptées **par famille**. */
  done_this_week: number;
}

export interface WorkoutSet {
  id: number;
  position: number;
  exercise_name: string;
  reps: number | null;
  duration_s: number | null;
  /** Passé au suivant. Distinct d'une série absente. */
  skipped: boolean;
}

export interface Workout {
  id: number;
  formula_id: number | null;
  formula_name: string;
  formula_family: string | null;
  started_at: string;
  ended_at: string | null;
  completed: boolean;
  /** Comptée à part, jamais confondue avec une séance faite. */
  cut_short: boolean;
  feeling: number | null;
  notes: string | null;
  duration_min: number | null;
  sets: WorkoutSet[];
}

export interface Proposal {
  formula: Formula | null;
  reason: string;
  alternatives: Formula[];
  /** Jours de surf d'affilée. Au-delà de trois, le renfo est écarté. */
  surf_streak: number;
}

export interface TrainingOverview {
  objectives: Objective[];
  formulas: Formula[];
  proposal: Proposal;
  recent: Workout[];
}
