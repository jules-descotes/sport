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
