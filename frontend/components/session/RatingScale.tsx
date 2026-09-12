"use client";

import { scoreClass } from "@/lib/format";

/**
 * Cinq grands boutons, de 1 à 5, aux couleurs de l'échelle de score.
 *
 * L'échelle est **le fil rouge du produit** : la même du 1 au 5 sur Jour, sur
 * Mer, sur la fiche spot et ici. Une note 4 posée à la main doit avoir
 * exactement la couleur d'une note 4 calculée par le moteur, sinon la
 * comparaison « ce que j'ai mis » / « ce qui était prévu » ne se fait plus à
 * l'œil, et c'est toute la promesse des statistiques du lot 6.
 *
 * Les boutons non choisis restent **neutres** plutôt que colorés en pâle : une
 * rangée de cinq cellules colorées dont une est « choisie » se lit comme une
 * jauge, pas comme un choix. Tant que rien n'est choisi, la rangée est grise ;
 * dès qu'on tape, une seule cellule porte sa couleur.
 */
interface RatingScaleProps {
  label: string;
  hint?: string;
  value: number | null;
  onChange: (value: number) => void;
  /** Nom accessible du groupe, si le libellé visible ne suffit pas. */
  name: string;
}

export function RatingScale({
  label,
  hint,
  value,
  onChange,
  name,
}: RatingScaleProps) {
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
          const selected = value === level;
          return (
            <button
              key={level}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={`${name} : ${level} sur 5`}
              onClick={() => onChange(level)}
              className={`tabular flex h-[58px] flex-1 items-center justify-center rounded-cell font-display text-[26px] font-bold leading-none transition-colors ${
                selected
                  ? `${scoreClass(level)} ring-2 ring-ink`
                  : "border border-line bg-card text-mute"
              }`}
            >
              {level}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
