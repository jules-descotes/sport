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
