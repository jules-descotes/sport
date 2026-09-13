import type { Thresholds } from "./types";

/**
 * **Teinter par qualité, pas par intensité.**
 *
 * Décidé le 13/09 (retours n° 4). Jusque-là, le tableau horaire teintait ses
 * cellules par magnitude : plus la houle est grosse, plus c'est saturé. C'est
 * exact, et c'est sans intérêt — une houle de 3 m est grosse, ce qui n'est pas
 * la même chose que bonne, et l'écran ne répondait donc jamais à la question
 * qu'on lui pose en l'ouvrant.
 *
 * Trois règles gouvernent tout ce fichier :
 *
 * 1. **Sous le minimum, c'est neutre.** Pas un palier bas de la rampe — un
 *    palier bas se lit comme « un peu de quelque chose de bien », alors qu'une
 *    période de 5 s n'est pas un peu de bonne période, c'est du clapot.
 * 2. **Le vent est le seul axe inversé**, parce que c'est le seul dont on veut
 *    moins. Sa rampe va de l'accent discret au gris-bleu sombre du séquentiel.
 *    **Jamais de rouge** : le rouge dit « danger » et un vent de 25 nœuds n'est
 *    pas un danger, c'est une mauvaise journée de surf.
 * 3. **L'énergie suit la houle.** Elle est proportionnelle à H²·T : lui donner
 *    sa propre rampe la ferait diverger de la hauteur qui la produit, et deux
 *    cellules de la même colonne se contrediraient.
 *
 * Ces fonctions lisent **les mêmes seuils** que ceux qui ont calculé la note
 * côté serveur (`services/scoring.py`), servis avec la prévision. Deux sources
 * pour la même règle finiraient par montrer une cellule « bonne » sous une
 * note de 2, et on mettrait des mois à comprendre pourquoi.
 */

/** Les seuils de Jules, quand le serveur ne les a pas encore envoyés. */
export const DEFAULT_THRESHOLDS: Thresholds = {
  period_good_s: 8,
  period_great_s: 12,
  wind_top_kt: 10,
  wind_strong_kt: 15,
  wind_very_strong_kt: 20,
  wave_min_m: 1.2,
  wave_good_m: 1.8,
  wave_big_m: 2.5,
};

/** La rampe séquentielle du CLAUDE.md : du plus pâle au plus saturé. */
const RAMP = ["seq-1", "seq-2", "seq-3", "seq-4", "seq-5", "seq-6"] as const;

/** Ni donnée, ni qualité : une case creuse. */
const EMPTY = "seq-empty";

/** Sous le minimum : la valeur existe, elle ne vaut simplement rien. */
const BELOW = "seq-quiet";

function missing(value: number | null | undefined): boolean {
  return value === null || value === undefined || Number.isNaN(value);
}

/**
 * Place une valeur sur la rampe depuis une liste de bornes **montantes**.
 *
 * Au-dessus de la dernière borne, on reste au palier le plus saturé : c'est
 * voulu. La rampe dit « c'est bon », et au-delà d'un certain point « encore
 * plus bon » n'a plus de sens — c'est la note, en bas du tableau, qui dit que
 * ça redevient injouable quand c'est trop gros.
 */
function ramp(value: number, steps: readonly number[]): string {
  let level = 0;
  for (const step of steps) {
    if (value >= step) level += 1;
  }
  if (level === 0) return BELOW;
  return RAMP[Math.min(level, RAMP.length - 1)];
}

/**
 * Période — « de mieux en mieux à partir de 8 s ».
 *
 * Cinq crans entre le « bon » et le « très bon » puis au-delà : c'est l'axe
 * où un écart d'une seconde se voit vraiment à l'eau.
 */
export function periodQualityClass(
  seconds: number | null | undefined,
  t: Thresholds,
): string {
  if (missing(seconds)) return EMPTY;
  const good = t.period_good_s;
  const great = t.period_great_s;
  const span = Math.max(great - good, 0.5);
  return ramp(seconds as number, [
    good,
    good + span * 0.4,
    good + span * 0.75,
    great,
    great + span * 0.5,
    great + span * 1.2,
  ]);
}

/**
 * Houle — « ça commence à 1,2 m, puis mieux en grossissant ».
 *
 * `wave_big_m` n'est pas un plafond de danger : c'est la taille que Jules
 * préfère. La rampe y arrive saturée et y reste — le fait qu'au-delà ça
 * redevienne injouable est dit par la **note**, qui redescend, et pas par une
 * couleur qui pâlirait sans qu'on sache si c'est « trop petit » ou « trop
 * gros ».
 */
export function waveQualityClass(
  meters: number | null | undefined,
  t: Thresholds,
): string {
  if (missing(meters)) return EMPTY;
  const min = t.wave_min_m;
  const good = t.wave_good_m;
  const big = t.wave_big_m;
  return ramp(meters as number, [
    min,
    min + (good - min) * 0.5,
    good,
    good + (big - good) * 0.5,
    big,
    big * 1.25,
  ]);
}

/**
 * Énergie — **la même classe que la houle qui la produit**.
 *
 * L'énergie vaut 0,49 × H² × T : elle n'a pas de seuils propres, et lui en
 * inventer ferait diverger deux cellules de la même colonne. On lui passe donc
 * la hauteur de l'heure, et elle porte sa teinte.
 */
export function energyQualityClass(
  meters: number | null | undefined,
  energyKj: number | null | undefined,
  t: Thresholds,
): string {
  if (missing(energyKj)) return EMPTY;
  return waveQualityClass(meters, t);
}

/**
 * Vent — **l'axe inversé**, et le seul.
 *
 * Sous `wind_top_kt` c'est parfait : accent discret, la seule cellule chaude
 * du tableau. Au-dessus, on remonte la rampe froide vers le gris-bleu sombre.
 * Jamais de rouge (règle C.2 du 13/09) : le rouge dit « danger », et un vent
 * de 25 nœuds n'est pas un danger, c'est une mauvaise journée de surf.
 */
export function windQualityClass(
  knots: number | null | undefined,
  t: Thresholds,
): string {
  if (missing(knots)) return EMPTY;
  const speed = knots as number;
  const top = t.wind_top_kt;
  const strong = t.wind_strong_kt;
  const veryStrong = t.wind_very_strong_kt;

  // La seule cellule chaude de tout le tableau : le vent qu'on espère.
  if (speed < top) return "wind-top";
  if (speed < top + (strong - top) * 0.5) return "seq-2";
  if (speed < strong) return "seq-3";
  if (speed < veryStrong) return "seq-4";
  if (speed < veryStrong * 1.35) return "seq-5";
  return "seq-6";
}

/** Ce que chaque teinte veut dire — la légende repliable sous le tableau. */
export interface LegendRow {
  axis: string;
  entries: { className: string; label: string }[];
}

function n(value: number, digits = 1): string {
  return value
    .toFixed(digits)
    .replace(/\.0$/, "")
    .replace(".", ",");
}

export function legendRows(t: Thresholds): LegendRow[] {
  return [
    {
      axis: "Houle",
      entries: [
        { className: BELOW, label: `moins de ${n(t.wave_min_m)} m` },
        { className: "seq-1", label: `${n(t.wave_min_m)} m` },
        { className: "seq-3", label: `${n(t.wave_good_m)} m` },
        { className: "seq-5", label: `${n(t.wave_big_m)} m` },
      ],
    },
    {
      axis: "Période",
      entries: [
        { className: BELOW, label: `moins de ${n(t.period_good_s, 0)} s` },
        { className: "seq-1", label: `${n(t.period_good_s, 0)} s` },
        { className: "seq-4", label: `${n(t.period_great_s, 0)} s` },
        { className: "seq-6", label: "au-delà" },
      ],
    },
    {
      axis: "Vent",
      entries: [
        { className: "wind-top", label: `moins de ${n(t.wind_top_kt, 0)} kt` },
        { className: "seq-3", label: `${n(t.wind_strong_kt, 0)} kt` },
        { className: "seq-4", label: `${n(t.wind_very_strong_kt, 0)} kt` },
        { className: "seq-6", label: "davantage" },
      ],
    },
  ];
}
