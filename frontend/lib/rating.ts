/**
 * Les règles de la notation en demi-points, hors de tout composant.
 *
 * Elles sont ici et pas dans `RatingScale` parce qu'elles se testent : le
 * cycle d'un bouton et le découpage horaire d'une session sont deux logiques
 * pures, et ce sont elles qui décident de ce qui finit en base.
 */

/** La note la plus basse. En dessous, ce n'est plus une note. */
export const MIN_RATING = 1;
/** La note la plus haute. 5 n'a pas de demi-point supérieur. */
export const MAX_RATING = 5;
export const RATING_STEP = 0.5;

/**
 * Ce que donne un tap sur le bouton `level`, selon la note courante.
 *
 * Le cycle d'un même bouton : entier → demi-point supérieur → entier. Toucher
 * un **autre** bouton repart de son entier — on choisit une note, on
 * n'incrémente pas un compteur, et c'est ce qui rend le geste prévisible.
 *
 * 5 n'a pas de demi-point supérieur : un second tap sur 5 le laisse à 5 plutôt
 * que de retomber à 4,5, qui serait une note qu'on n'a pas demandée.
 */
export function cycleRating(level: number, current: number | null): number {
  if (current === level && level < MAX_RATING) return level + RATING_STEP;
  if (current === level + RATING_STEP) return level;
  return level;
}

/** Vrai quand la valeur est une note valide : 1 à 5, par pas de 0,5. */
export function isValidRating(value: number): boolean {
  if (value < MIN_RATING || value > MAX_RATING) return false;
  return Math.abs(value * 2 - Math.round(value * 2)) < 1e-9;
}

/**
 * Les heures pleines **entamées** entre deux instants.
 *
 * « Entamée » et pas « pleine » : une session de 8 h 15 à 10 h 40 a vécu
 * l'heure de 10 h, et elle mérite sa ligne. C'est la même règle que la fenêtre
 * du `conditions_snapshot` côté serveur, et il faut que les deux coïncident —
 * sinon une heure notée n'aurait aucune condition à laquelle s'apparier.
 *
 * Bornée à douze : au-delà, ce n'est plus une session, c'est une erreur de
 * saisie, et une frise de trente lignes ne se remplirait jamais.
 */
export function startedHours(start: Date, end: Date, max = 12): Date[] {
  const first = new Date(start);
  first.setMinutes(0, 0, 0);

  const hours: Date[] = [];
  for (
    const hour = new Date(first);
    hour < end && hours.length < max;
    hour.setHours(hour.getHours() + 1)
  ) {
    hours.push(new Date(hour));
  }
  return hours;
}
