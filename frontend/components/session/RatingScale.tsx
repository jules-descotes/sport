"use client";

import { useRef } from "react";

import { num, scoreClass } from "@/lib/format";
import { MAX_RATING, RATING_STEP, cycleRating } from "@/lib/rating";

/**
 * Cinq grands boutons, de 1 à 5 — et les demi-points par-dessus.
 *
 * L'échelle est **le fil rouge du produit** : la même du 1 au 5 sur Jour, sur
 * Surf, sur la fiche spot et ici. Une note 4 posée à la main doit avoir
 * exactement la couleur d'une note 4 calculée par le moteur, sinon la
 * comparaison « ce que j'ai mis » / « ce qui était prévu » ne se fait plus à
 * l'œil, et c'est toute la promesse des statistiques du lot 6.
 *
 * Les boutons non choisis restent **neutres** plutôt que colorés en pâle : une
 * rangée de cinq cellules colorées dont une est « choisie » se lit comme une
 * jauge, pas comme un choix. Tant que rien n'est choisi, la rangée est grise ;
 * dès qu'on tape, une seule cellule porte sa couleur.
 *
 * **Les demi-points** (décidé le 13/09 — « 3 ou 4 » ne suffisait pas à
 * départager deux sessions d'une même semaine) n'ajoutent **aucun bouton** :
 * cinq cibles de 58 px tiennent sur 390 px, dix n'y tiendraient pas, et la
 * rangée deviendrait un clavier. Un second tap sur le bouton déjà choisi — ou
 * un appui long — donne le demi-point supérieur, et le bouton affiche « 3,5 ».
 * Un troisième tap revient à l'entier : le geste est réversible sans chercher.
 *
 * 5 n'a pas de demi-point supérieur : un second tap sur 5 ne fait rien plutôt
 * que de retomber à 4,5, ce qui serait une note qu'on n'a pas demandée.
 */
interface RatingScaleProps {
  label: string;
  hint?: string;
  /** La note, de 1 à 5 par pas de 0,5. */
  value: number | null;
  onChange: (value: number) => void;
  /** Nom accessible du groupe, si le libellé visible ne suffit pas. */
  name: string;
  /** Rangée compacte, pour la frise heure par heure. */
  compact?: boolean;
}

/** Durée d'appui à partir de laquelle on tient le demi-point. */
const LONG_PRESS_MS = 380;

export function RatingScale({
  label,
  hint,
  value,
  onChange,
  name,
  compact = false,
}: RatingScaleProps) {
  const longPress = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fired = useRef(false);

  const startLongPress = (level: number) => {
    fired.current = false;
    longPress.current = setTimeout(() => {
      fired.current = true;
      if (level < MAX_RATING) onChange(level + RATING_STEP);
    }, LONG_PRESS_MS);
  };

  const endLongPress = () => {
    if (longPress.current !== null) {
      clearTimeout(longPress.current);
      longPress.current = null;
    }
  };

  return (
    <fieldset className="min-w-0">
      <legend className="flex w-full items-baseline justify-between gap-3 pb-2">
        <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {label}
        </span>
        {hint ? <span className="text-[12px] text-mute">{hint}</span> : null}
      </legend>

      <div className="flex gap-2" role="radiogroup" aria-label={name}>
        {[1, 2, 3, 4, 5].map((level) => {
          // Le bouton porte sa valeur entière **et** le demi-point au-dessus :
          // 3,5 s'affiche dans la case du 3, parce que c'est de là qu'il vient.
          const selected = value === level || value === level + RATING_STEP;
          const shown = selected ? (value as number) : level;
          return (
            <button
              key={level}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={`${name} : ${num(shown, shown % 1 ? 1 : 0)} sur 5`}
              onClick={() => {
                // L'appui long a déjà décidé : le clic qui le suit ne doit pas
                // repasser derrière et annuler le demi-point.
                if (fired.current) {
                  fired.current = false;
                  return;
                }
                onChange(cycleRating(level, value));
              }}
              onPointerDown={() => startLongPress(level)}
              onPointerUp={endLongPress}
              onPointerLeave={endLongPress}
              onPointerCancel={endLongPress}
              // Sans ça, l'appui long ouvre le menu contextuel d'iOS par-dessus.
              onContextMenu={(event) => event.preventDefault()}
              className={`tabular flex flex-1 items-center justify-center rounded-cell font-display font-bold leading-none transition-colors ${
                compact ? "h-touch text-[18px]" : "h-[58px] text-[26px]"
              } ${
                selected
                  ? `${scoreClass(shown)} ring-2 ring-ink`
                  : "border border-line bg-card text-mute"
              }`}
            >
              {num(shown, shown % 1 ? 1 : 0)}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
