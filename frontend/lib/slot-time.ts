/**
 * Ce qui, dans un créneau, relève de l'heure qu'il est.
 *
 * Depuis le 13/09 l'écran Jour montre **la journée entière, depuis ce matin**,
 * et non plus ce qu'il en reste : la fenêtre de `/recommend` s'ouvrait à
 * `now - 2 h`, si bien qu'à 14 h les quatre premières colonnes de la bande
 * étaient vides. La matinée n'était pas absente de la base — elle n'était pas
 * demandée.
 *
 * Montrer le passé oblige à le marquer : sans quoi un 4,5 à 9 h se lit à 14 h
 * comme une invitation. D'où cette règle, à part et testée plutôt que glissée
 * dans un composant : elle se trompe d'un cran sans que personne ne le voie.
 */

/** Durée d'un créneau de la bande de l'écran Jour, en heures. */
export const SLOT_SPAN_HOURS = 3;

/**
 * Ce créneau est-il **révolu** ?
 *
 * Un créneau ne l'est qu'une fois **entièrement** écoulé : à 14 h, celui de
 * 12 h court encore, et l'éteindre reviendrait à barrer l'heure qu'on est en
 * train de vivre.
 *
 * Le pas est un paramètre et non une constante en dur : la bande de Jour
 * avance par trois heures, le tableau de Surf par une.
 */
export function slotIsPast(
  iso: string,
  now: Date,
  spanHours: number = SLOT_SPAN_HOURS,
): boolean {
  const end = new Date(iso).getTime() + spanHours * 3_600_000;
  return end <= now.getTime();
}
