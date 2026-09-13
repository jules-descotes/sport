"use client";

import { IconChevronDown } from "@/components/ui/Icons";
import {
  WAVE_LENGTHS,
  WAVE_LENGTH_LABELS,
  WAVE_SHAPES,
  WAVE_SHAPE_LABELS,
  WAVE_SIZES,
  WAVE_SIZE_LABELS,
} from "@/lib/types";
import type { WaveLength, WaveShape, WaveSize, WaveType } from "@/lib/types";

/**
 * **Décrire les vagues** — trois axes, trois contrôles segmentés, repliés.
 *
 * Décidé le 13/09 (retours n° 3). Ce qu'ils décrivent n'est mesuré par aucune
 * API : un modèle de vagues donne une hauteur de houle au large, il ne dit pas
 * si ça a déferlé creux ou mou — et c'est souvent là que se joue la différence
 * entre une bonne et une mauvaise session. Seul quelqu'un qui était dans l'eau
 * peut le dire.
 *
 * **Repliés, et c'est le point.** Le risque du projet est la friction de
 * saisie, pas la rareté des données : 240 sessions par an, et tout écran qui
 * dépasse quinze secondes tue le jeu de données (cf. PROJET.md §7.2). Trois
 * champs de plus dépliés par défaut coûteraient trois regards à chaque
 * notation, même quand on ne veut rien dire. Repliés, ils ne coûtent qu'une
 * ligne — et un tap le jour où on a quelque chose à décrire.
 *
 * Trois valeurs par axe, pas cinq : on les saisit une main sur la planche, et
 * personne ne sait départager « assez creuse » de « plutôt creuse ».
 *
 * **Un second tap sur le choix courant le retire.** Sans ça, une valeur posée
 * par erreur ne se reprend jamais — et « non renseigné » n'est pas « moyen » :
 * c'est exactement la distinction que ces champs existent pour préserver.
 */

type Axis<T extends string> = {
  label: string;
  values: readonly T[];
  labels: Record<T, string>;
  current: T | null;
  onPick: (value: T | null) => void;
};

function SegmentedAxis<T extends string>({
  label,
  values,
  labels,
  current,
  onPick,
}: Axis<T>) {
  return (
    <fieldset>
      <legend className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {label}
      </legend>
      <div
        className="flex gap-2"
        role="radiogroup"
        aria-label={label}
        data-testid={`wave-axis-${label.toLowerCase()}`}
      >
        {values.map((value) => {
          const selected = current === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onPick(selected ? null : value)}
              className={`min-h-touch flex-1 rounded-cell border px-2 text-[15px] font-semibold ${
                selected
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              {labels[value]}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function WaveTypeFields({
  value,
  onChange,
  open,
  onToggle,
  title = "Décrire les vagues",
}: {
  value: WaveType;
  onChange: (next: WaveType) => void;
  open: boolean;
  onToggle: () => void;
  title?: string;
}) {
  const described =
    [value.wave_size, value.wave_length, value.wave_shape].filter(Boolean)
      .length;

  const set = (patch: Partial<WaveType>) => onChange({ ...value, ...patch });

  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 text-left"
      >
        <span className="text-[15px] font-semibold text-ink-2">
          {title}
          {described > 0 ? (
            // Replié, l'écran doit dire qu'il y a quelque chose dedans —
            // sinon une description posée puis oubliée devient invisible.
            <span className="tabular pl-2 text-[13px] font-normal text-mute">
              {described} sur 3
            </span>
          ) : null}
        </span>
        <IconChevronDown
          className={`h-5 w-5 shrink-0 text-mute transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open ? (
        <div className="mt-3 flex flex-col gap-4">
          <SegmentedAxis<WaveSize>
            label="Taille"
            values={WAVE_SIZES}
            labels={WAVE_SIZE_LABELS}
            current={value.wave_size}
            onPick={(wave_size) => set({ wave_size })}
          />
          <SegmentedAxis<WaveLength>
            label="Longueur"
            values={WAVE_LENGTHS}
            labels={WAVE_LENGTH_LABELS}
            current={value.wave_length}
            onPick={(wave_length) => set({ wave_length })}
          />
          <SegmentedAxis<WaveShape>
            label="Forme"
            values={WAVE_SHAPES}
            labels={WAVE_SHAPE_LABELS}
            current={value.wave_shape}
            onPick={(wave_shape) => set({ wave_shape })}
          />
          <p className="text-[13px] leading-snug text-mute">
            Ce que les instruments ne mesurent pas. Tout est optionnel — ne
            rien dire vaut mieux que dire à peu près.
          </p>
        </div>
      ) : null}
    </>
  );
}
