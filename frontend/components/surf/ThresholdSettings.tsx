"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconChevronDown } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { DEFAULT_THRESHOLDS } from "@/lib/quality-colors";
import type { Thresholds } from "@/lib/types";

/**
 * **Tes seuils** — où commence le bon, en huit nombres.
 *
 * Décidé le 13/09 (retours n° 4). Ils font deux choses à la fois, et c'est
 * exprès : ils teintent les cellules du tableau horaire **et** ils calculent
 * la note. Un seul jeu de nombres pour les deux — deux jeux finiraient par
 * montrer une cellule « bonne » sous une note de 2.
 *
 * Réglés à la molette, jamais au clavier : c'est la règle du produit
 * (`PROJET.md` §1, règle 5), et elle vaut ici comme ailleurs — on ne tape pas
 * « 1,2 » sur un pavé numérique pour régler une préférence.
 *
 * Les valeurs de départ sont celles que Jules a données. On peut toujours y
 * revenir d'un tap : un réglage qu'on ne sait plus défaire, on n'y touche pas.
 */

type Axis = {
  key: keyof Thresholds;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  unit: string;
  digits: number;
};

const GROUPS: { title: string; note: string; axes: Axis[] }[] = [
  {
    title: "Houle",
    note: "Ça commence, c'est bon, c'est la taille que tu préfères.",
    axes: [
      {
        key: "wave_min_m",
        label: "Ça commence",
        hint: "en dessous, la cellule reste neutre",
        min: 0.2,
        max: 4,
        step: 0.1,
        unit: "m",
        digits: 1,
      },
      {
        key: "wave_good_m",
        label: "C'est bon",
        hint: "",
        min: 0.3,
        max: 6,
        step: 0.1,
        unit: "m",
        digits: 1,
      },
      {
        key: "wave_big_m",
        label: "C'est gros",
        hint: "la taille que tu préfères, pas un plafond",
        min: 0.5,
        max: 8,
        step: 0.1,
        unit: "m",
        digits: 1,
      },
    ],
  },
  {
    title: "Période",
    note: "De mieux en mieux à partir du premier seuil.",
    axes: [
      {
        key: "period_good_s",
        label: "Bon",
        hint: "en dessous, c'est du clapot",
        min: 4,
        max: 16,
        step: 0.5,
        unit: "s",
        digits: 0,
      },
      {
        key: "period_great_s",
        label: "Très bon",
        hint: "",
        min: 5,
        max: 22,
        step: 0.5,
        unit: "s",
        digits: 0,
      },
    ],
  },
  {
    title: "Vent",
    note: "Le seul axe inversé : moins il y en a, mieux c'est.",
    axes: [
      {
        key: "wind_top_kt",
        label: "Top",
        hint: "la seule cellule chaude du tableau",
        min: 2,
        max: 25,
        step: 1,
        unit: "kt",
        digits: 0,
      },
      {
        key: "wind_strong_kt",
        label: "Fort",
        hint: "",
        min: 4,
        max: 35,
        step: 1,
        unit: "kt",
        digits: 0,
      },
      {
        key: "wind_very_strong_kt",
        label: "Très fort",
        hint: "",
        min: 6,
        max: 45,
        step: 1,
        unit: "kt",
        digits: 0,
      },
    ],
  },
];

function value(n: number, digits: number): string {
  return n.toFixed(digits).replace(".", ",");
}

function Stepper({
  axis,
  current,
  onChange,
}: {
  axis: Axis;
  current: number;
  onChange: (next: number) => void;
}) {
  const bump = (delta: number) => {
    const next = Math.round((current + delta) / axis.step) * axis.step;
    onChange(Math.min(axis.max, Math.max(axis.min, Number(next.toFixed(3)))));
  };

  return (
    <div className="flex items-center gap-3 border-t border-line py-2 first:border-0">
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-semibold text-ink">
          {axis.label}
        </span>
        {axis.hint ? (
          <span className="block text-[12px] leading-snug text-mute">
            {axis.hint}
          </span>
        ) : null}
      </span>

      <span className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => bump(-axis.step)}
          aria-label={`${axis.label} : diminuer`}
          className="flex h-touch w-touch items-center justify-center rounded-button border border-line bg-card text-[20px] font-semibold text-ink-2"
        >
          −
        </button>
        <span className="tabular w-[68px] text-center font-display text-[20px] font-bold text-ink">
          {value(current, axis.digits)}
          <span className="pl-1 text-[13px] font-normal text-mute">
            {axis.unit}
          </span>
        </span>
        <button
          type="button"
          onClick={() => bump(axis.step)}
          aria-label={`${axis.label} : augmenter`}
          className="flex h-touch w-touch items-center justify-center rounded-button border border-line bg-card text-[20px] font-semibold text-ink-2"
        >
          +
        </button>
      </span>
    </div>
  );
}

export function ThresholdSettings() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Thresholds | null>(null);

  const stored = useQuery({
    queryKey: ["thresholds"],
    queryFn: api.thresholds,
  });

  const save = useMutation({
    mutationFn: (next: Thresholds) => api.updateThresholds(next),
    onSuccess: (saved) => {
      setDraft(null);
      queryClient.setQueryData(["thresholds"], saved);
      // La prévision porte les seuils et les notes : elles changent toutes les
      // deux, il faut la redemander.
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
    },
  });

  const current = draft ?? stored.data ?? DEFAULT_THRESHOLDS;
  const dirty = draft !== null;

  const set = (key: keyof Thresholds, next: number) =>
    setDraft({ ...current, [key]: next });

  /**
   * Le refus du serveur quand les seuils d'un même axe se croisent.
   *
   * Vérifié ici aussi, pour que le bouton le dise avant l'aller-retour — mais
   * la règle reste celle du serveur : une validation de formulaire n'est pas
   * une contrainte.
   */
  const ordered =
    current.period_great_s > current.period_good_s &&
    current.wind_top_kt < current.wind_strong_kt &&
    current.wind_strong_kt < current.wind_very_strong_kt &&
    current.wave_min_m < current.wave_good_m &&
    current.wave_good_m < current.wave_big_m;

  return (
    <section className="px-5 pb-6">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 text-left"
      >
        <span>
          <span className="block text-[12px] font-semibold uppercase tracking-wide text-mute">
            Tes seuils
          </span>
          <span className="block text-[14px] text-ink-2">
            Où commence le bon — couleurs du tableau et notes
          </span>
        </span>
        <IconChevronDown
          className={`h-5 w-5 shrink-0 text-mute transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open ? (
        <div className="mt-3 rounded-card border border-line bg-card px-4 py-3">
          {GROUPS.map((group) => (
            <div key={group.title} className="pb-3">
              <h3 className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
                {group.title}
              </h3>
              <p className="pb-1 text-[12px] leading-snug text-mute">
                {group.note}
              </p>
              {group.axes.map((axis) => (
                <Stepper
                  key={axis.key}
                  axis={axis}
                  current={current[axis.key]}
                  onChange={(next) => set(axis.key, next)}
                />
              ))}
            </div>
          ))}

          {!ordered ? (
            <p className="pb-2 text-[13px] text-ink-2">
              Les seuils d&apos;un même axe doivent aller en montant.
            </p>
          ) : null}

          {save.error ? (
            <p className="pb-2 text-[13px] text-ink-2">
              Enregistrement impossible pour le moment.
            </p>
          ) : null}

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              disabled={!dirty || !ordered || save.isPending}
              onClick={() => save.mutate(current)}
              className="flex min-h-touch flex-1 items-center justify-center rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-40"
            >
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
            <button
              type="button"
              onClick={() => setDraft(DEFAULT_THRESHOLDS)}
              className="min-h-touch rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
            >
              Défauts
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
