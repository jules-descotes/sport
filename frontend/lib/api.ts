import type {
  ApiToken,
  BodyMetric,
  ApiTokenCreated,
  DailyLogEntry,
  DailyLogStatus,
  DailyLogToday,
  DayExpenditureData,
  Discipline,
  Exercise,
  ExerciseCategory,
  Food,
  FoodHit,
  GenerateResponse,
  GroupLevel,
  FoodLogEntry,
  Formula,
  GearType,
  GearWithUsage,
  Habit,
  HabitEvent,
  HabitKind,
  HabitPeriod,
  MatchWindow,
  Meal,
  MealPlan,
  NutritionDay,
  NutritionGoal,
  NutritionProfile,
  Objective,
  ProfileStats,
  Proposal,
  Recipe,
  Recommendation,
  SessionJournal,
  SessionSegmentValue,
  SessionStatus,
  SlotDetail,
  Spot,
  SpotForecast,
  SpotHit,
  SpotNearby,
  SpotPreferences,
  SpotRules,
  SurfSession,
  Thresholds,
  TideCoefficientDay,
  TrainingOverview,
  WeighInResponse,
  User,
  WaveLength,
  WaveShape,
  WaveSize,
  Workout,
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
  /** De 1 à 5 par pas de 0,5. Le serveur refuse tout autre pas. */
  rating_conditions?: number;
  rating_personal?: number;
  /** Absent = ne touche pas aux segments existants ; liste vide = les efface.
   *  Les deux gestes sont distincts, et l'écran de notation ne doit pas
   *  effacer une frise saisie la veille. */
  segments?: SessionSegmentValue[];
  gear_id?: number;
  wave_count?: number;
  notes?: string | null;
  /** Type de vagues — descripteurs des conditions observées, tous optionnels.
   *  `null` efface l'axe : « non renseigné » n'est pas « moyen ». */
  wave_size?: WaveSize | null;
  wave_length?: WaveLength | null;
  wave_shape?: WaveShape | null;
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

  /** `step_hours: 3` sert la grille 5 jours × 8 créneaux de l'écran Surf :
   *  quarante points au lieu de cent vingt, sur un réseau de parking de plage. */
  spotForecast: (ref: string | number, days = 5, stepHours = 1) =>
    request<SpotForecast>(
      `/spots/${ref}/forecast${query({ days, step_hours: stepHours })}`,
    ),

  /** Le détail d'un créneau. N'ingère rien : le créneau vient d'un tableau
   *  déjà affiché, donc d'une prévision déjà en base. */
  spotSlot: (ref: string | number, ts: string) =>
    request<SlotDetail>(`/spots/${ref}/slot${query({ ts })}`),

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

  /** La dépense estimée du jour — surf et séances. Sous `/expenditure` et
   *  pas sous `/nutrition` : c'est l'écran Jour qui la regarde le matin, et
   *  c'est le même calcul qui alimente la cible calorique. */
  expenditure: (day?: string) =>
    request<DayExpenditureData>(`/expenditure${query({ day })}`),

  /** Les seuils de qualité — huit nombres qui teintent le tableau horaire
   *  **et** calculent les notes. La ligne est créée aux défauts à la première
   *  lecture : l'écran de réglage n'a jamais deux cas à distinguer. */
  thresholds: () => request<Thresholds>("/auth/me/thresholds"),

  /** Correction partielle : le serveur repart des valeurs en place. */
  updateThresholds: (data: Partial<Thresholds>) =>
    request<Thresholds>("/auth/me/thresholds", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

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

  /** Réordonne les favoris. La liste est **complète** : un déplacement relatif
   *  ferait dépendre le résultat de l'ordre d'arrivée de deux requêtes. */
  reorderFavorites: (spotIds: number[]) =>
    request<SpotHit[]>("/spots/favorites/order", {
      method: "PUT",
      body: JSON.stringify({ spot_ids: spotIds }),
    }),

  /** Les critères d'un spot. Un jeu vide quand rien n'a été saisi — jamais
   *  un 404 : le formulaire s'ouvre pareil dans les deux cas. */
  spotRules: (ref: string | number) =>
    request<SpotRules>(`/spots/${ref}/rules`),

  /** Enregistre les critères **en entier**. C'est ce qui permet d'effacer un
   *  critère : dans un envoi partiel, `null` voudrait dire à la fois « ne
   *  change pas » et « retire ». */
  setSpotRules: (ref: string | number, rules: Omit<SpotRules, "spot_id">) =>
    request<SpotRules>(`/spots/${ref}/rules`, {
      method: "PUT",
      body: JSON.stringify(rules),
    }),

  clearSpotRules: (ref: string | number) =>
    request<void>(`/spots/${ref}/rules`, { method: "DELETE" }),

  /** Les créneaux à venir qui correspondent aux critères des favoris.
   *  N'ingère rien : les favoris sont déjà ingérés toutes les trois heures. */
  spotMatches: (days = 3) =>
    request<MatchWindow[]>(`/spots/matches${query({ days })}`),

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

  // ── Marées ────────────────────────────────────────────────────────────

  /** Les coefficients des pleines mers, jour par jour.
   *
   *  Pas de spot en paramètre, et ce n'est pas un oubli : le coefficient est
   *  national par définition — le SHOM le calcule à Brest et il vaut de
   *  Dunkerque à Hendaye. */
  tideCoefficients: (start?: string, days = 5) =>
    request<TideCoefficientDay[]>(`/tides/coefficients${query({ start, days })}`),

  // ── Sessions ──────────────────────────────────────────────────────────

  /** Tout ce dont l'écran Jour a besoin, en un aller-retour : les sessions à
   *  noter (de n'importe quel jour) et celles d'aujourd'hui. */
  sessionJournal: () => request<SessionJournal>("/sessions/today"),

  sessions: (
    params: {
      status?: SessionStatus;
      since?: string;
      until?: string;
      /** Filtre de l'historique : un seul spot. */
      spot_id?: number;
      /** Filtre de l'historique : note **de conditions** minimale. */
      min_rating?: number;
      /** Filtres de type de vagues. Le serveur regarde la session **et** ses
       *  segments : une session molle dans l'ensemble mais creuse à 11 h
       *  ressort sur « creuses ». */
      wave_size?: WaveSize;
      wave_length?: WaveLength;
      wave_shape?: WaveShape;
      limit?: number;
      offset?: number;
    } = {},
  ) => request<SurfSession[]>(`/sessions${query(params)}`),

  /** Ce qui est en corbeille, et encore restaurable. */
  trashedSessions: () => request<SurfSession[]>("/sessions/trash"),

  /** Sort une session de la corbeille, telle qu'elle y est entrée. */
  restoreSession: (id: number) =>
    request<SurfSession>(`/sessions/${id}/restore`, { method: "POST" }),

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
    segments?: SessionSegmentValue[];
    gear_id?: number;
    wave_count?: number;
    notes?: string;
    client_uuid?: string;
    wave_size?: WaveSize | null;
    wave_length?: WaveLength | null;
    wave_shape?: WaveShape | null;
  }) =>
    request<SurfSession>("/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** Met la session à la corbeille — trente jours, puis purge. */
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

  /** Ce qui est envoyé est ce qui change — le reste ne bouge pas en base.
   *  Un champ absent n'est pas un champ vidé : `null` efface pour de bon. */
  updateGear: (
    id: number,
    data: {
      name?: string;
      gear_type?: GearType;
      length_m?: number | null;
      volume_l?: number | null;
      discipline?: Discipline;
      purchased_on?: string | null;
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

  // ── Training ──────────────────────────────────────────────────────────

  /** Tout l'écran Training en un aller-retour. Sème le catalogue au premier
   *  appel : le conteneur Railway redémarre à froid, on ne fait pas ce
   *  travail à chaque démarrage. */
  trainingOverview: () => request<TrainingOverview>("/training/overview"),

  /** La proposition du jour, seule — ce que l'écran Jour affiche. */
  trainingToday: () => request<Proposal>("/training/today"),

  /** Une mesure d'objectif. Une par jour : re-mesurer remplace. */
  addMeasurement: (
    objectiveId: number,
    data: { value: number; measured_on?: string; note?: string },
  ) =>
    request<Objective>(`/training/objectives/${objectiveId}/measurements`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** La bibliothèque, consultable. Source et licence sur chaque ligne. */
  exercises: (params: { q?: string; category?: ExerciseCategory } = {}) =>
    request<Exercise[]>(`/training/exercises${query(params)}`),

  /** Ouvre une séance. Le nom de la formule est figé à cet instant. */
  startWorkout: (formulaId: number) =>
    request<Workout>("/training/workouts", {
      method: "POST",
      body: JSON.stringify({ formula_id: formulaId }),
    }),

  /** Clôt une séance. **Le serveur** décide si elle est complète, à partir
   *  des séries réellement faites — jamais le client. */
  finishWorkout: (
    id: number,
    data: {
      feeling?: number;
      notes?: string;
      sets: {
        position: number;
        exercise_id?: number;
        formula_item_id?: number;
        exercise_name: string;
        reps?: number | null;
        duration_s?: number | null;
        skipped: boolean;
      }[];
    },
  ) =>
    request<Workout>(`/training/workouts/${id}/finish`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** Supprime une séance ouverte par erreur. */
  deleteWorkout: (id: number) =>
    request<void>(`/training/workouts/${id}`, { method: "DELETE" }),

  /** Le niveau de chaque groupe, **déduit** de ce qui a été fait. Huit lignes,
   *  toujours : un groupe jamais travaillé apparaît quand même, au niveau 2. */
  trainingLevels: () => request<GroupLevel[]>("/training/levels"),

  /** Corriger un niveau, ou rendre la main à la déduction (`level: null`). */
  setTrainingLevel: (group: string, level: number | null) =>
    request<GroupLevel[]>("/training/levels", {
      method: "PUT",
      body: JSON.stringify({ group, level }),
    }),

  /** Trois séances, ou moins — jamais trois fois la même. Déterministe :
   *  fermer l'écran et le rouvrir rend exactement les mêmes. */
  composeWorkout: (data: {
    groups: string[];
    duration_min?: number;
    equipment?: string[];
    intent?: string;
    variant?: number;
  }) =>
    request<GenerateResponse>("/training/compose", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** Sauve une séance générée comme formule personnelle. Elle est régénérée
   *  côté serveur depuis la demande : une formule est de la donnée
   *  d'apprentissage, elle ne vient pas du client. */
  saveComposedWorkout: (data: {
    key: string;
    name: string;
    groups: string[];
    duration_min?: number;
    equipment?: string[];
    intent?: string;
    variant?: number;
  }) =>
    request<Formula>("/training/compose/save", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  workouts: (limit = 50) =>
    request<Workout[]>(`/training/workouts${query({ limit })}`),

  // ── Nutrition ─────────────────────────────────────────────────────────

  /** Tout l'écran Nutrition pour une journée, en un seul aller-retour. */
  nutritionDay: (day?: string) =>
    request<NutritionDay>(`/nutrition/day${query({ day })}`),

  /** Recherche d'aliment. Sans requête, les vingt plus journalisés — l'écran
   *  s'ouvre sur ce qu'on mange, pas sur une liste vide. */
  searchFoods: (q = "") => request<FoodHit[]>(`/nutrition/foods${query({ q })}`),

  /** Le produit derrière un code-barres, mis en cache au premier scan. */
  scanBarcode: (barcode: string) =>
    request<Food>(`/nutrition/barcode/${encodeURIComponent(barcode)}`),

  addFoodLog: (data: {
    day?: string;
    meal?: Meal;
    food_id?: number;
    recipe_id?: number;
    quantity_g?: number;
    servings?: number;
    label?: string;
  }) =>
    request<FoodLogEntry>("/nutrition/log", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteFoodLog: (id: number) =>
    request<void>(`/nutrition/log/${id}`, { method: "DELETE" }),

  recipes: (params: { meal?: Meal; tag?: string } = {}) =>
    request<Recipe[]>(`/nutrition/recipes${query(params)}`),

  mealPlan: (week?: string) =>
    request<MealPlan>(`/nutrition/plan${query({ week })}`),

  /** (Re)génère la semaine. Un glouton sous contrainte, pas une IA. */
  generateMealPlan: (week?: string) =>
    request<MealPlan>(`/nutrition/plan${query({ week })}`, { method: "POST" }),

  /** Remplace **un** repas : un menu qu'il faut régénérer en entier pour
   *  corriger un dîner se jette. */
  regenerateMeal: (day_index: number, meal: Meal, week?: string) =>
    request<MealPlan>(`/nutrition/plan/regenerate${query({ week })}`, {
      method: "POST",
      body: JSON.stringify({ day_index, meal }),
    }),

  weighIns: () => request<BodyMetric[]>("/nutrition/weight"),

  /** La pesée — et la recalibration qu'elle déclenche. */
  addWeighIn: (data: {
    day?: string;
    weight_kg?: number;
    waist_cm?: number;
    note?: string;
  }) =>
    request<WeighInResponse>("/nutrition/weight", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  nutritionProfile: () => request<NutritionProfile>("/nutrition/profile"),

  updateNutritionProfile: (data: {
    goal?: NutritionGoal;
    activity_factor?: number;
    protein_g_per_kg?: number;
    fat_ratio?: number;
    birth_date?: string | null;
    sex?: string | null;
    height_m?: number;
  }) =>
    request<NutritionProfile>("/nutrition/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── Habitudes et statistiques ─────────────────────────────────────────

  /** Les habitudes et leurs compteurs du jour. En pause exclues par défaut :
   *  l'écran Jour ne montre que ce qui est en cours. */
  habits: (includePaused = false) =>
    request<Habit[]>(`/habits${query({ include_paused: includePaused })}`),

  createHabit: (data: {
    name: string;
    icon?: string;
    kind?: HabitKind;
    unit?: string | null;
    target?: number | null;
    target_period?: HabitPeriod;
  }) => request<Habit>("/habits", { method: "POST", body: JSON.stringify(data) }),

  updateHabit: (
    id: number,
    data: {
      name: string;
      icon?: string;
      kind?: HabitKind;
      unit?: string | null;
      target?: number | null;
      target_period?: HabitPeriod;
      is_active?: boolean;
      position?: number;
    },
  ) =>
    request<Habit>(`/habits/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteHabit: (id: number) =>
    request<void>(`/habits/${id}`, { method: "DELETE" }),

  /** Un tap. Rend l'habitude **avec son compteur à jour** : recharger toute la
   *  liste ferait clignoter la rangée de pastilles à chaque geste. */
  addHabitEvent: (id: number, quantity = 1, note?: string) =>
    request<Habit>(`/habits/${id}/events`, {
      method: "POST",
      body: JSON.stringify({ quantity, note }),
    }),

  habitEvents: (id: number) =>
    request<HabitEvent[]>(`/habits/${id}/events`),

  /** Les quatre cartes du profil. Rien n'est stocké : tout se recalcule. */
  profileStats: () => request<ProfileStats>("/habits/stats"),

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
