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
  /** Ce dont Mifflin-St Jeor a besoin (lot 5). Nuls : la cible se rabat sur
   *  une estimation, et le dit. */
  birth_date: string | null;
  sex: string | null;
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
  /** Ce qu'on a vu en sondant l'URL au moment de la poser : « le site répond
   *  404 », « le site renvoie X-Frame-Options: DENY ». Nul le reste du temps.
   *  Un avertissement, jamais un refus — le site peut répondre autrement au
   *  téléphone qu'à une requête partie du serveur. */
  webcam_warning?: string | null;
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

// ── Seuils personnels de qualité (décidé le 13/09, retours n° 4) ─────────
//
// Huit nombres qui disent **où commence le bon**, pour Jules. Ils teintent le
// tableau horaire (`lib/quality-colors.ts`) et ils calculent la note côté
// serveur (`services/scoring.py`) — les mêmes, servis avec la prévision, parce
// que deux sources pour la même règle finiraient par montrer une cellule
// « bonne » sous une note de 2.

export interface Thresholds {
  /** La période s'améliore à partir de là. En dessous : du clapot. */
  period_good_s: number;
  period_great_s: number;
  /** Le seul axe inversé : moins il y en a, mieux c'est. */
  wind_top_kt: number;
  wind_strong_kt: number;
  wind_very_strong_kt: number;
  /** « Ça commence » — en dessous, la cellule reste neutre. */
  wave_min_m: number;
  wave_good_m: number;
  /** La taille qu'il préfère, pas un plafond de danger. */
  wave_big_m: number;
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
  /** Les seuils qui ont calculé les notes — et qui teintent les cellules.
   *  Servis avec la prévision plutôt que demandés à part : c'est une requête
   *  de moins à l'ouverture de l'écran, sur un réseau de parking de plage. */
  thresholds: Thresholds | null;
  points: ForecastPoint[];
}

// ── Classement des favoris (13/09, retours n° 4) ─────────────────────────
//
// La note de journée est un **produit** : part des heures de jour qui
// correspondent aux critères du spot × qualité moyenne sur ces heures. Un spot
// excellent une heure par jour et un spot correct toute la journée ne se
// départagent pas par addition.

export interface FavoriteDayRanking {
  day: string;
  daylight_hours: number;
  matching_hours: number;
  /** Vaut 1 pour un spot sans critères : on ne peut pas la calculer, et la
   *  mettre à zéro le ferait disparaître du classement. */
  match_ratio: number;
  average_score: number;
  day_score: number;
  best_ts: string | null;
  best_score: number | null;
  window_start: string | null;
  window_end: string | null;
}

export interface FavoriteRankingEntry {
  spot: Spot;
  /** Faux = classé sur le seul score, et l'écran le signale. */
  has_rules: boolean;
  is_home: boolean;
  /** Faux = jamais ingéré. Rangé en bas et **pas noté** : lui inventer une
   *  note serait pire que de n'en donner aucune. */
  has_forecast: boolean;
  best_day_score: number;
  days: FavoriteDayRanking[];
}

export interface RulesPreview {
  days: number;
  matching_hours: number;
  daylight_hours: number;
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
  /** L'aperçu immédiat rendu à l'enregistrement : « sur les 3 prochains
   *  jours, ça matcherait N heures ». Nul sur une simple lecture. */
  preview?: RulesPreview | null;
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
// ── Le type de vagues (décidé le 13/09, retours n° 3) ────────────────────
//
// Trois axes optionnels saisis à la notation, repliés derrière un lien : le
// chemin des quinze secondes ne s'allonge pas, il gagne un endroit où aller
// quand on a le temps.
//
// **Ce sont des descripteurs des conditions observées, pas des étiquettes de
// confort.** Aucune API ne les mesure — un modèle de vagues donne une hauteur
// au large, il ne dit pas si ça a déferlé creux ou mou. C'est ce qui les rend
// exploitables au lot 3 comme cibles auxiliaires (prédire « creuse » depuis la
// période et le vent), et ce qui interdit de les donner en entrée au modèle
// moyen terme : ils n'existent pas au moment de la prédiction.

export const WAVE_SIZES = ["small", "medium", "large"] as const;
export type WaveSize = (typeof WAVE_SIZES)[number];

export const WAVE_LENGTHS = ["short", "medium", "long"] as const;
export type WaveLength = (typeof WAVE_LENGTHS)[number];

export const WAVE_SHAPES = ["hollow", "mushy", "crumbling"] as const;
export type WaveShape = (typeof WAVE_SHAPES)[number];

export const WAVE_SIZE_LABELS: Record<WaveSize, string> = {
  small: "Petites",
  medium: "Moyennes",
  large: "Grandes",
};

export const WAVE_LENGTH_LABELS: Record<WaveLength, string> = {
  short: "Courtes",
  medium: "Moyennes",
  long: "Longues",
};

export const WAVE_SHAPE_LABELS: Record<WaveShape, string> = {
  hollow: "Creuses",
  mushy: "Molles",
  crumbling: "Déferlantes",
};

/** Les trois axes, portés aussi bien par la session que par un segment. */
export interface WaveType {
  wave_size: WaveSize | null;
  wave_length: WaveLength | null;
  wave_shape: WaveShape | null;
}

export interface SessionSegmentValue extends WaveType {
  started_at: string;
  rating_conditions: number | null;
  rating_personal: number | null;
}

export interface SurfSession extends WaveType {
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
  /** Le nom d'origine. Gardé pour retrouver l'exercice dans sa base : un
   *  « Développé couché à la barre » ne se cherche pas sur wger sous ce
   *  nom-là. **Ce n'est pas ce qu'on affiche** — voir `name_fr`. */
  name: string;
  slug: string;
  /** Le nom **affiché**, toujours. Nul quand on n'a pas su le dire en
   *  français, et l'exercice n'est alors jamais proposé (`eligible`). */
  name_fr: string | null;
  description_fr: string | null;
  category: ExerciseCategory;
  muscle_group: string | null;
  instructions: string | null;
  image_url: string | null;
  /** Les deux photos de free-exercise-db : départ et arrivée. C'est leur
   *  alternance qui montre le mouvement. */
  images: string[];
  /** Toujours renseignés : `builtin`, `wger`, `free-exercise-db`. */
  source: string;
  license: string | null;
  source_url: string | null;
  /** L'auteur de l'image, quand la licence demande de le nommer (CC BY,
   *  CC BY-SA). Nul pour wger et free-exercise-db, qui publient au nom du
   *  projet, et pour les pictogrammes dessinés dans l'application. */
  image_author: string | null;

  // ── Taxonomie (13/09) ───────────────────────────────────────────────────
  group_key: string;
  pattern: string;
  equipment: string;
  /** 1 à 5. 3 par défaut, et c'est assumé. */
  difficulty: number;
  /** `temps` ou `reps` : un gainage se tient, une traction se compte. */
  effort_kind: string;
  /** « Par côté » double la durée d'une séance. */
  unilateral: boolean;
  /** Nom français **et** image. Non éligible = consultable, jamais proposé. */
  eligible: boolean;
  group_label: string;
  pattern_label: string;
  equipment_label: string;
}

// ── Le générateur de séances (décidé le 13/09, retours n° 3) ─────────────

export const EXERCISE_GROUPS = [
  "abdos",
  "dos",
  "epaules",
  "jambes",
  "hanches",
  "poitrine",
  "bras",
  "corps-entier",
] as const;
export type ExerciseGroup = (typeof EXERCISE_GROUPS)[number];

export const EXERCISE_GROUP_LABELS: Record<ExerciseGroup, string> = {
  abdos: "Abdos",
  dos: "Dos",
  epaules: "Épaules",
  jambes: "Jambes",
  hanches: "Hanches",
  poitrine: "Poitrine",
  bras: "Bras",
  "corps-entier": "Corps entier",
};

export const EQUIPMENTS = [
  "aucun",
  "elastique",
  "halteres",
  "barre-traction",
  "kettlebell",
  "machine",
] as const;
export type EquipmentKey = (typeof EQUIPMENTS)[number];

export const EQUIPMENT_LABELS: Record<EquipmentKey, string> = {
  aucun: "Aucun",
  elastique: "Élastique",
  halteres: "Haltères",
  "barre-traction": "Barre de traction",
  kettlebell: "Kettlebell",
  machine: "Machine",
};

export const INTENTS = ["entretien", "progression", "recuperation"] as const;
export type Intent = (typeof INTENTS)[number];

export const INTENT_LABELS: Record<Intent, string> = {
  entretien: "Entretien",
  progression: "Progression",
  recuperation: "Récupération",
};

/** Le niveau d'un groupe, **et d'où il vient**. La provenance est affichée :
 *  « déduit de 14 séries » se discute, « niveau 3 » ne se discute pas. */
export interface GroupLevel {
  group: string;
  group_label: string;
  level: number;
  /** `deduit` · `defaut` · `manuel` */
  origin: string;
  sets_counted: number;
  best_reps: number | null;
  best_seconds: number | null;
}

export interface GeneratedItem {
  exercise: Exercise;
  sets: number;
  reps: number | null;
  duration_s: number | null;
  rest_s: number;
  note: string | null;
  /** Les deux minutes d'échauffement, prises dans la mobilité du groupe. */
  warmup: boolean;
}

export interface GeneratedWorkout {
  key: string;
  name: string;
  /** La ligne qui justifie la séance. Pas de la décoration : une proposition
   *  qu'on ne comprend pas se remplace au hasard. */
  principle: string;
  duration_min: number;
  items: GeneratedItem[];
}

export interface GenerateResponse {
  workouts: GeneratedWorkout[];
  levels: GroupLevel[];
  pool_size: number;
  /** Pourquoi il n'y a rien à proposer, en clair. Un écran blanc n'apprend
   *  rien. */
  reasons: string[];
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

// ── Dépense estimée du jour (décidé le 13/09, retours n° 4) ──────────────
//
// **Estimée**, et le mot est affiché. Rien de ce qui compose ce chiffre n'est
// mesuré : le MET vient du compendium d'activités physiques, la durée est
// arrondie au quart d'heure, et la taille des vagues est un souvenir. La même
// estimation alimente la cible calorique — un second calcul « pour
// l'affichage » finirait par donner deux chiffres pour la même journée.

export interface ExpenditureItem {
  kind: "surf" | "workout";
  label: string;
  minutes: number;
  met: number;
  kcal: number;
  /** Ce qui a modulé le MET, en clair : « grandes vagues », « renfo ». */
  detail: string | null;
}

export interface DayExpenditureData {
  surf_min: number;
  surf_kcal: number;
  workout_min: number;
  workout_kcal: number;
  total_kcal: number;
  items: ExpenditureItem[];
  weight_kg: number;
  /** Vrai quand le poids vient d'un défaut faute de pesée. */
  weight_estimated: boolean;
}

// ── Nutrition ────────────────────────────────────────────────────────────

/** Les quatre repas d'une journée, dans l'ordre où ils se vivent. Ils servent
 *  au **journal** : on note ce qu'on mange, petit déjeuner et en-cas compris. */
export const MEALS = ["breakfast", "lunch", "snack", "dinner"] as const;
export type Meal = (typeof MEALS)[number];

/** Ceux que le **menu** planifie, et c'est tout.
 *
 *  Un petit déjeuner ne se choisit pas le dimanche pour le mardi — il se
 *  répète. Un en-cas planifié est un en-cas qu'on ne mange pas. Les deux
 *  continuent de se journaliser, ils ne se prévoient plus. */
export const PLANNED_MEALS = ["lunch", "dinner"] as const;
export type PlannedMeal = (typeof PLANNED_MEALS)[number];

export const MEAL_LABELS: Record<Meal, string> = {
  breakfast: "Petit déj",
  lunch: "Déjeuner",
  snack: "En-cas",
  dinner: "Dîner",
};

/** Un aliment — Ciqual ou Open Food Facts. Valeurs **pour 100 g**. */
export interface Food {
  id: number;
  name: string;
  food_group: string | null;
  brand: string | null;
  barcode: string | null;
  source: string;
  kcal_100g: number | null;
  protein_100g: number | null;
  carb_100g: number | null;
  fat_100g: number | null;
  fiber_100g: number | null;
}

export interface FoodHit extends Food {
  /** Nombre de fois journalisé : ce qui remonte en tête de liste. */
  recent_count: number;
}

/** Une ligne du journal. Ses valeurs sont **figées à la saisie** : un bilan de
 *  la semaine dernière ne change pas parce qu'une base a bougé. */
export interface FoodLogEntry {
  id: number;
  day: string;
  meal: Meal;
  food_id: number | null;
  recipe_id: number | null;
  label: string;
  quantity_g: number;
  kcal: number | null;
  protein_g: number | null;
  carb_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
  created_at: string;
}

export interface MacroTotals {
  kcal: number;
  protein_g: number;
  carb_g: number;
  fat_g: number;
  fiber_g: number;
}

export interface Expenditure {
  surf_min: number;
  surf_kcal: number;
  workout_min: number;
  workout_kcal: number;
  total_kcal: number;
}

/** La cible du jour **et de quoi elle est faite**. Une cible qui monte de
 *  400 kcal sans dire pourquoi n'est pas croyable, et une cible pas croyable
 *  ne se suit pas. */
export interface NutritionTarget {
  kcal: number;
  protein_g: number;
  carb_g: number;
  fat_g: number;
  protein_g_per_kg: number | null;
  bmr: number;
  base_kcal: number;
  goal_kcal: number;
  calibration_kcal: number;
  expenditure: Expenditure;
  estimated: boolean;
  reasons: string[];
}

/** L'unité dans laquelle une chose **s'achète**. Le gramme reste la grandeur
 *  stockée ; la pièce et le millilitre sont des conversions d'affichage. */
export type BuyUnit = "g" | "piece" | "ml";

export interface RecipeItem {
  label: string;
  quantity_g: number;
  food_id: number | null;
  unit: BuyUnit;
  quantity: number;
  /** « œufs », « bananes ». Nul pour les grammes et les millilitres. */
  unit_label: string | null;
}

export interface Recipe {
  id: number;
  slug: string;
  name: string;
  meals: Meal[];
  tags: string[];
  servings: number;
  prep_min: number;
  steps: string | null;
  /** Par portion. Nulles tant que Ciqual n'est pas importé — la recette reste
   *  lisible, sans ses macros. */
  kcal: number | null;
  protein_g: number | null;
  carb_g: number | null;
  fat_g: number | null;
  items: RecipeItem[];
  /** `catalog` (semée par l'app) ou `user` (écrite ou modifiée ici). Modifier
   *  une recette du catalogue en crée une copie : le semis réécrit les siennes,
   *  jamais les nôtres. */
  source: "catalog" | "user";
  based_on_id: number | null;
  favorite: boolean;
  note: string | null;
  cooked_count: number;
}

export interface RecipeItemWrite {
  label: string;
  quantity_g: number;
  /** Le nom cherché dans Ciqual. À défaut, on cherche le libellé lui-même. */
  ciqual_query?: string;
}

/** Une recette écrite ou modifiée à la main. Tous les champs sont facultatifs :
 *  on corrige une quantité sans réécrire la recette. Les macros n'y sont
 *  **jamais** — elles se déduisent des ingrédients, elles ne se saisissent pas. */
export interface RecipeWrite {
  name?: string;
  meals?: Meal[];
  tags?: string[];
  servings?: number;
  prep_min?: number;
  steps?: string | null;
  items?: RecipeItemWrite[];
}

/** `planned` : un plat est prévu · `away` : pas chez soi, rien à prévoir et
 *  **rien à acheter**. */
export type SlotStatus = "planned" | "away";

export interface MealPlanItem {
  day_index: number;
  meal: PlannedMeal;
  servings: number;
  /** Nulle quand le créneau est `away`, ou quand il reste à remplir. Un
   *  créneau vide est un état du menu, pas une anomalie. */
  recipe: Recipe | null;
  status: SlotStatus;
}

export interface ShoppingLine {
  label: string;
  /** Le total agrégé, toujours — c'est la grandeur vraie. */
  quantity_g: number;
  food_group: string | null;
  unit: BuyUnit;
  quantity: number;
  unit_label: string | null;
}

export interface MealPlan {
  week_start: string;
  items: MealPlanItem[];
  shopping: ShoppingLine[];
}

export interface NutritionDay {
  day: string;
  target: NutritionTarget;
  totals: MacroTotals;
  entries: FoodLogEntry[];
  planned: MealPlanItem[];
}

export interface BodyMetric {
  id: number;
  day: string;
  weight_kg: number | null;
  waist_cm: number | null;
  photo_url: string | null;
  note: string | null;
}

/** Ce qu'a donné la recalibration déclenchée par une pesée. Elle ne fait rien
 *  la plupart du temps, et le dit. */
export interface Calibration {
  applied: boolean;
  days: number;
  weight_change_kg: number;
  expected_change_kg: number;
  adjustment_kcal: number;
  new_calibration_kcal: number;
  reason: string;
}

export interface WeighInResponse {
  metric: BodyMetric;
  calibration: Calibration;
}

export type NutritionGoal = "maintain" | "cut" | "bulk";

export interface NutritionProfile {
  goal: NutritionGoal;
  activity_factor: number;
  protein_g_per_kg: number;
  fat_ratio: number;
  calibration_kcal: number;
  calibrated_on: string | null;
}

// ── Habitudes ────────────────────────────────────────────────────────────

export type HabitKind = "count" | "check";
export type HabitPeriod = "day" | "week";

/**
 * Un compteur libre, défini par Jules.
 *
 * L'objectif est **facultatif**, et c'est tout l'esprit : une habitude sans
 * objectif est une habitude qu'on observe, pas qu'on se fixe. Rien de jugeant
 * n'arrive du serveur — ni série, ni taux de réussite.
 */
export const HABIT_DIRECTIONS = ["min", "max"] as const;
export type HabitDirection = (typeof HABIT_DIRECTIONS)[number];

export interface Habit {
  id: number;
  name: string;
  icon: string;
  kind: HabitKind;
  unit: string | null;
  target: number | null;
  target_period: HabitPeriod;
  /** `min` — au moins tant. `max` — au plus tant (13/09, retours n° 4).
   *  **L'affichage est identique dans les deux cas** : un compteur, un
   *  objectif, une tendance. Le sens change le libellé et rien d'autre. */
  target_direction: HabitDirection;
  position: number;
  is_active: boolean;
  /** Compteur du jour, et de la semaine pour les objectifs hebdomadaires. */
  today: number;
  week: number;
}

export interface HabitEvent {
  id: number;
  habit_id: number;
  occurred_at: string;
  quantity: number;
  note: string | null;
}

export interface HabitTrend {
  habit_id: number;
  name: string;
  icon: string;
  unit: string | null;
  kind: HabitKind;
  target: number | null;
  target_period: HabitPeriod;
  target_direction: HabitDirection;
  total_30d: number;
  days_with_activity: number;
  /** Moyennes par jour. **La tendance suffit** dans les stats de profil : une
   *  moyenne à 7 jours plus basse que celle à 30 se lit toute seule, dans les
   *  deux sens, sans qu'on ait à dire si c'est bien. */
  average_7d: number;
  average_30d: number;
  /** Trente valeurs, du plus ancien au plus récent. La courbe, et rien
   *  d'autre : on observe, on n'évalue pas. */
  daily: number[];
}

export interface SurfStats {
  sessions_30d: number;
  hours_30d: number;
  sessions_season: number;
  hours_season: number;
  /** `null` et pas 0 : une moyenne sans session n'existe pas. */
  average_rating: number | null;
  top_spot: string | null;
  top_spot_sessions: number;
  streak_days: number;
  best_rating: number | null;
  best_spot: string | null;
  best_day: string | null;
}

export interface NutritionStats {
  logged_days_30d: number;
  on_target_days_30d: number;
  average_protein_g: number | null;
  weight_kg: number | null;
  weight_change_30d: number | null;
}

export interface WeekCount {
  week_start: string;
  done: number;
  planned: number;
}

export interface TrainingStats {
  weeks: WeekCount[];
  done_8w: number;
  planned_8w: number;
  best_objective: string | null;
  best_ratio: number | null;
}

export interface ProfileStats {
  day: string;
  surf: SurfStats;
  nutrition: NutritionStats;
  training: TrainingStats;
  habits: HabitTrend[];
}
