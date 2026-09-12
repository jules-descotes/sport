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
 * Le fil rouge est identique partout : accueil, comparateur, fiche spot.
 */
export function scoreClass(level: number | null | undefined): string {
  const clamped = Math.min(5, Math.max(1, Math.round(level ?? 1)));
  return `score-${clamped}`;
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
 * locale**. La bande de l'écran Jour et la grille de l'écran Mer sont des
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
 */
export function boardLength(lengthM: number | null | undefined): string {
  if (lengthM === null || lengthM === undefined) return "";
  const totalInches = lengthM / 0.0254;
  let feet = Math.floor(totalInches / 12);
  let inches = Math.round(totalInches - feet * 12);
  // 11,6 pouces arrondis donnent 12 : c'est un pied de plus, pas un 6'12.
  if (inches === 12) {
    feet += 1;
    inches = 0;
  }
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
