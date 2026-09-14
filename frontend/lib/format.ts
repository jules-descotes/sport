/**
 * Mise en forme française et conversions d'affichage.
 *
 * Les heures sont stockées en UTC en base ; la conversion en heure locale est
 * faite **ici, côté front, jamais en base** (cf. CLAUDE.md). Les marées et les
 * créneaux de surf n'ont de sens qu'en heure locale pour l'utilisateur.
 */

const JOURS = [
  "dimanche",
  "lundi",
  "mardi",
  "mercredi",
  "jeudi",
  "vendredi",
  "samedi",
];

/** Rose des vents en français, 16 secteurs — mêmes libellés que le back. */
const ROSE = [
  "N",
  "NNE",
  "NE",
  "ENE",
  "E",
  "ESE",
  "SE",
  "SSE",
  "S",
  "SSO",
  "SO",
  "OSO",
  "O",
  "ONO",
  "NO",
  "NNO",
];

export function compass(deg: number | null | undefined): string {
  if (deg === null || deg === undefined) return "—";
  return ROSE[Math.floor((((deg % 360) + 360) % 360 + 11.25) / 22.5) % 16];
}

/** Nombre à la française : virgule décimale, jamais de point. */
export function num(
  value: number | null | undefined,
  decimals = 1,
  fallback = "—",
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return fallback;
  }
  return value.toFixed(decimals).replace(".", ",");
}

export function hourLabel(iso: string): string {
  const date = new Date(iso);
  return `${date.getHours()} h`;
}

export function shortHour(iso: string): string {
  return String(new Date(iso).getHours()).padStart(2, "0");
}

export function dayKey(iso: string): string {
  const date = new Date(iso);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

export function dayLabel(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const days = Math.round(
    (new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() -
      new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) /
      86_400_000,
  );
  if (days === 0) return "Auj.";
  if (days === 1) return "Demain";
  return JOURS[date.getDay()].slice(0, 3);
}

export function fullDayLabel(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const days = Math.round(
    (new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() -
      new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) /
      86_400_000,
  );
  if (days === 0) return "Aujourd'hui";
  if (days === 1) return "Demain";
  return JOURS[date.getDay()];
}

/**
 * Classe de couleur d'une note, échelle 1 → 5 du CLAUDE.md.
 *
 * Le fil rouge est identique partout : accueil, comparateur, fiche spot.
 *
 * Depuis le 13/09, l'échelle porte les **demi-points** : 3,5 rend `score-35`,
 * dont la couleur est le mélange des paliers 3 et 4 (`globals.css`). La note
 * est arrondie au demi-point le plus proche et non à l'entier — une note
 * calculée à 3,47 tombe sur 3,5, ce qui est la granularité de l'échelle.
 */
export function scoreClass(level: number | null | undefined): string {
  const clamped = Math.min(5, Math.max(1, level ?? 1));
  const half = Math.round(clamped * 2) / 2;
  return Number.isInteger(half)
    ? `score-${half}`
    : `score-${Math.floor(half)}5`;
}

/** Une note telle qu'on l'écrit : « 4 », « 3,5 ». Jamais « 4,0 ». */
export function ratingLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return num(value, value % 1 === 0 ? 0 : 1);
}

export function distanceLabel(km: number | null | undefined): string {
  if (km === null || km === undefined) return "";
  return km < 10 ? `${num(km, 1)} km` : `${Math.round(km)} km`;
}

export function tideLabel(rising: boolean | null | undefined): string {
  if (rising === null || rising === undefined) return "marée étale";
  return rising ? "marée montante" : "marée descendante";
}

/**
 * Les huit créneaux d'une journée, toutes les trois heures, en **heure
 * locale**. La bande de l'écran Jour et la grille de l'écran Surf sont des
 * matrices : les colonnes sont fixes, et une heure sans prévision s'éteint au
 * lieu de disparaître, sinon toute la lecture se décale.
 */
export const SLOT_HOURS = [0, 3, 6, 9, 12, 15, 18, 21] as const;

/** Le créneau de trois heures auquel appartient une heure locale. */
export function slotHour(iso: string): number {
  return Math.floor(new Date(iso).getHours() / 3) * 3;
}

/**
 * « de terre » ou « de mer », à partir de la composante offshore signée.
 *
 * Le front ne connaît pas l'orientation de la côte — elle est calculée depuis
 * le trait de côte OSM et vit côté back. Il reçoit donc le verdict, pas les
 * ingrédients. Sous deux nœuds de composante, le vent longe la côte et ni
 * « terre » ni « mer » ne serait honnête.
 */
export function windSideLabel(
  offshoreKt: number | null | undefined,
): string | null {
  if (offshoreKt === null || offshoreKt === undefined) return null;
  if (offshoreKt > 2) return "de terre";
  if (offshoreKt < -2) return "de mer";
  return "de travers";
}

/**
 * Heure de la pleine mer la plus proche, lue sur le niveau de la mer.
 *
 * Open-Meteo donne un niveau heure par heure, pas une table de marées : la
 * pleine mer est le maximum local. On la cherche sur la journée du créneau de
 * référence, ce qui suppose des points horaires — d'où la prévision non
 * échantillonnée sur l'écran Jour.
 */
export function highTideAfter<T extends { ts: string; sea_level_m: number | null }>(
  points: T[],
  from: Date,
): string | null {
  const usable = points.filter(
    (point) => point.sea_level_m !== null && new Date(point.ts) >= from,
  );
  if (usable.length < 3) return null;

  for (let index = 1; index < usable.length - 1; index += 1) {
    const previous = usable[index - 1].sea_level_m as number;
    const current = usable[index].sea_level_m as number;
    const next = usable[index + 1].sea_level_m as number;
    if (current >= previous && current >= next) return usable[index].ts;
  }
  return null;
}

/**
 * Longueur de planche : mètres en base, pieds et pouces à l'écran.
 *
 * La base ne stocke pas de « 6'2 » — c'est une unité composite, deux nombres
 * et deux unités dans un seul champ, et le CLAUDE.md l'interdit. Mais aucun
 * surfeur ne dit « ma 1,88 m ». La conversion est donc un affichage, au même
 * titre que celle des heures UTC en heure locale : la base porte la grandeur,
 * le front porte la coutume.
 *
 * L'arrondi vit ici, une seule fois : la carte du matos l'affiche et la
 * molette de correction s'en sert pour se pré-remplir. Deux arrondis
 * divergents feraient lire 6'2 à un écran et 6'1 à l'autre pour la même
 * planche — et corriger le volume d'une planche en changerait la longueur.
 */
export function boardFeetInches(lengthM: number): {
  feet: number;
  inches: number;
} {
  const totalInches = lengthM / 0.0254;
  let feet = Math.floor(totalInches / 12);
  let inches = Math.round(totalInches - feet * 12);
  // 11,6 pouces arrondis donnent 12 : c'est un pied de plus, pas un 6'12.
  if (inches === 12) {
    feet += 1;
    inches = 0;
  }
  return { feet, inches };
}

/** La même chose, écrite — « 6'2 ». */
export function boardLength(lengthM: number | null | undefined): string {
  if (lengthM === null || lengthM === undefined) return "";
  const { feet, inches } = boardFeetInches(lengthM);
  return `${feet}'${inches}`;
}

/** L'inverse, pour la molette de saisie du matos. */
export function lengthFromFeet(feet: number, inches: number): number {
  return Math.round((feet * 12 + inches) * 0.0254 * 1000) / 1000;
}

/** « 1 h 45 », « 45 min ». Jamais « 105 min » : personne ne lit ça. */
export function durationLabel(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${String(rest).padStart(2, "0")}`;
}

/** Heure locale à la minute — « 09:30 ». La base est en UTC. */
export function clockLabel(iso: string): string {
  const date = new Date(iso);
  return `${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;
}

const MOIS = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];

/** « 12 sept. » — et l'année seulement si ce n'est pas celle-ci. */
export function shortDate(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const base = `${date.getDate()} ${MOIS[date.getMonth()]}`;
  return date.getFullYear() === now.getFullYear()
    ? base
    : `${base} ${String(date.getFullYear()).slice(2)}`;
}

/** Fin d'une session, depuis son début et sa durée. */
export function sessionEnd(startIso: string, durationMin: number | null): Date {
  const start = new Date(startIso);
  return new Date(start.getTime() + (durationMin ?? 0) * 60_000);
}

/** Minutes écoulées entre deux instants, arrondies au quart d'heure.
 *  Les molettes de saisie vont par quinze minutes : la durée aussi. */
export function minutesBetween(start: Date, end: Date): number {
  return Math.round((end.getTime() - start.getTime()) / 60_000);
}

/** Arrondit un instant au quart d'heure inférieur — le pas des molettes. */
export function floorToQuarter(date: Date): Date {
  const rounded = new Date(date);
  rounded.setMinutes(Math.floor(rounded.getMinutes() / 15) * 15, 0, 0);
  return rounded;
}

/**
 * Teinte d'intensité — le séquentiel du CLAUDE.md, six paliers.
 *
 * **Ce n'est pas l'échelle de score**, et la distinction est le cœur de la
 * lisibilité du tableau horaire : l'échelle 1 → 5 dit « c'est bon », le
 * séquentiel dit « c'est gros ». Les teinter pareil ferait lire une houle de
 * 3 m comme une bonne nouvelle, alors qu'elle peut être injouable.
 *
 * Les cellules de hauteur et de vent portent donc le séquentiel ; seule la
 * ligne du bas porte l'échelle de score (règle C.1 du 13/09).
 */
const SEQ_CLASSES = [
  "seq-1",
  "seq-2",
  "seq-3",
  "seq-4",
  "seq-5",
  "seq-6",
] as const;

function seqClass(
  value: number | null | undefined,
  steps: readonly number[],
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "seq-empty";
  }
  let level = 0;
  for (const step of steps) {
    if (value >= step) level += 1;
  }
  return SEQ_CLASSES[Math.min(level, SEQ_CLASSES.length - 1)];
}

/** Paliers de hauteur de houle, en mètres. Calés sur la côte landaise :
 *  en dessous de 40 cm il ne se passe rien, au-dessus de 3 m c'est du gros. */
const WAVE_STEPS = [0.4, 0.8, 1.3, 2.0, 3.0] as const;

/** Paliers de vent, en nœuds. 4 kt = mer lisse, 25 kt = coup de vent. */
const WIND_STEPS = [4, 9, 14, 20, 27] as const;

export function waveHeightClass(height_m: number | null | undefined): string {
  return seqClass(height_m, WAVE_STEPS);
}

export function windSpeedClass(speed_kt: number | null | undefined): string {
  return seqClass(speed_kt, WIND_STEPS);
}

/** « de terre » / « de mer », en une lettre pour une cellule étroite. */
export function windSideShort(
  offshoreKt: number | null | undefined,
): "terre" | "mer" | "travers" | null {
  if (offshoreKt === null || offshoreKt === undefined) return null;
  if (offshoreKt > 2) return "terre";
  if (offshoreKt < -2) return "mer";
  return "travers";
}

/** Un écart signé, avec son signe explicite : « +0,3 », « −20 ». */
export function signed(
  value: number | null | undefined,
  decimals = 1,
  unit = "",
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  // Le vrai signe moins typographique, pas le trait d'union du clavier.
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const body = Math.abs(value).toFixed(decimals).replace(".", ",");
  return `${sign}${body}${unit}`;
}

/** La clé de jour d'une date locale — « 2026-09-13 ». Sert d'ancre au
 *  défilement du tableau horaire. */
export function localDayKey(iso: string): string {
  const date = new Date(iso);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(
    2,
    "0",
  )}-${String(date.getDate()).padStart(2, "0")}`;
}

/**
 * Le coefficient de marée tel qu'il s'affiche : « 95 », ou « ≈ 95 ».
 *
 * Le « ≈ » n'est pas de la coquetterie. L'écart mesuré contre l'annuaire SHOM
 * (`docs/COEFFICIENT-MAREE.md`) est de six points au pire, et un chiffre
 * approximatif annoncé comme exact est pire qu'un chiffre absent : celui-ci,
 * on sait qu'on ne peut pas s'y fier au point près, et on peut quand même
 * distinguer une vive-eau d'une morte-eau, ce qui est l'usage réel.
 */
export function coefficientLabel(
  value: number | null | undefined,
  approximate = false,
): string {
  if (value === null || value === undefined) return "—";
  return approximate ? `≈ ${value}` : String(value);
}

/**
 * L'énergie de houle telle qu'elle s'affiche : une décimale sous 10, aucune
 * au-dessus. Même règle que la ligne « Énergie » du tableau horaire — à 46
 * kJ/s/m, la décimale ne dit plus rien.
 */
export function energyLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return num(value, value < 10 ? 1 : 0);
}
