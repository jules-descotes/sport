"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconSliders, IconTrash } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import {
  SECTORS_8,
  TIDE_PHASES,
  type Sector8,
  type SpotRules,
  type TidePhase,
} from "@/lib/types";

/**
 * **Les critères de Jules**, saisis sur la fiche spot (décidé le 13/09).
 *
 * « Parlementia marche en houle d'ouest de 1,2 à 2,5 m, période au moins 11 s,
 * vent d'est, marée montante. » Cette phrase-là, aucun modèle ne l'apprendra
 * avant plusieurs saisons — et il l'a déjà.
 *
 * Trois partis pris d'écran, et ils viennent tous de la même règle :
 *
 * 1. **Zéro clavier.** Molettes pour les nombres, pastilles pour les secteurs
 *    et les phases. Les critères se saisissent souvent au retour d'une
 *    session, parfois sur le parking.
 * 2. **Vide veut dire « pas de contrainte ».** Chaque curseur porte une
 *    position « — » à son extrémité basse, et c'est celle par défaut. On ne
 *    pose pas de seuil par défaut : un seuil inventé serait pris pour une
 *    observation dès le lendemain.
 * 3. **Huit secteurs, pas seize.** On ne saisit pas « 285° » sur une plage, on
 *    saisit « ouest ». La rose à seize points sert à lire, celle à huit à
 *    écrire.
 */

const PHASE_LABELS: Record<TidePhase, string> = {
  low: "Basse",
  rising: "Montante",
  high: "Pleine",
  falling: "Descendante",
};

/** Hauteurs proposées, en mètres. « — » d'abord : c'est le défaut. */
const HEIGHTS = [null, 0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0];
const PERIODS = [null, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18];
const WINDS = [null, 5, 8, 10, 12, 15, 18, 20, 25, 30];
const HOURS = [null, ...Array.from({ length: 24 }, (_, hour) => hour)];

type Draft = Omit<SpotRules, "spot_id" | "updated_at">;

const EMPTY: Draft = {
  wave_height_min_m: null,
  wave_height_max_m: null,
  wave_period_min_s: null,
  swell_sectors: [],
  wind_sectors: [],
  wind_max_kt: null,
  tide_phases: [],
  hour_min: null,
  hour_max: null,
};

function isEmpty(draft: Draft): boolean {
  return (
    draft.wave_height_min_m === null &&
    draft.wave_height_max_m === null &&
    draft.wave_period_min_s === null &&
    draft.swell_sectors.length === 0 &&
    draft.wind_sectors.length === 0 &&
    draft.wind_max_kt === null &&
    draft.tide_phases.length === 0 &&
    draft.hour_min === null &&
    draft.hour_max === null
  );
}

/**
 * Un choix parmi une liste de valeurs, en pastilles défilantes.
 *
 * Pas un `<input type="number">` : le pavé numérique d'iOS recouvre la moitié
 * de l'écran, et il n'y a rien à saisir au clavier ici — les seuils utiles
 * sont une douzaine de valeurs rondes.
 */
function ValuePicker<T extends number | null>({
  label,
  unit,
  values,
  value,
  onChange,
  decimals = 1,
}: {
  label: string;
  unit: string;
  values: readonly T[];
  value: T;
  onChange: (value: T) => void;
  decimals?: number;
}) {
  return (
    <div className="pt-3">
      <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-wide text-mute">
        {label} <span className="font-normal normal-case">{unit}</span>
      </p>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {values.map((candidate) => {
          const active = candidate === value;
          return (
            <button
              key={String(candidate)}
              type="button"
              onClick={() => onChange(candidate)}
              aria-pressed={active}
              className={`tabular min-h-touch shrink-0 rounded-pill border px-3.5 text-[15px] font-semibold ${
                active
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              {candidate === null ? "—" : num(candidate as number, decimals)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChipGroup<T extends string>({
  label,
  hint,
  options,
  selected,
  render,
  onToggle,
}: {
  label: string;
  hint: string;
  options: readonly T[];
  selected: T[];
  render: (option: T) => string;
  onToggle: (option: T) => void;
}) {
  return (
    <div className="pt-3">
      <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-wide text-mute">
        {label}{" "}
        <span className="font-normal normal-case">
          {selected.length === 0 ? hint : ""}
        </span>
      </p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const active = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              onClick={() => onToggle(option)}
              aria-pressed={active}
              className={`min-h-touch shrink-0 rounded-pill border px-3.5 text-[15px] font-semibold ${
                active
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              {render(option)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function SpotRulesForm({ slug }: { slug: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const rules = useQuery({
    queryKey: ["spot-rules", slug],
    queryFn: () => api.spotRules(slug),
  });

  // Le brouillon est **dérivé** tant que rien n'a été touché : `draft` reste
  // nul jusqu'au premier geste, et l'écran montre ce qui est enregistré. Le
  // recopier dans un état à l'arrivée de la réponse effacerait une saisie en
  // cours si le serveur répondait entre-temps — et un état par défaut n'est
  // pas un état.
  const loaded = rules.data;

  const save = useMutation({
    mutationFn: (next: Draft) => api.setSpotRules(slug, next),
    onSuccess: (saved) => {
      queryClient.setQueryData(["spot-rules", slug], saved);
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      queryClient.invalidateQueries({ queryKey: ["spot-hourly", slug] });
      setOpen(false);
    },
  });

  const clear = useMutation({
    mutationFn: () => api.clearSpotRules(slug),
    onSuccess: () => {
      setDraft(EMPTY);
      queryClient.invalidateQueries({ queryKey: ["spot-rules", slug] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      queryClient.invalidateQueries({ queryKey: ["spot-hourly", slug] });
    },
  });

  const current: Draft =
    draft ??
    (loaded
      ? {
          wave_height_min_m: loaded.wave_height_min_m,
          wave_height_max_m: loaded.wave_height_max_m,
          wave_period_min_s: loaded.wave_period_min_s,
          swell_sectors: loaded.swell_sectors,
          wind_sectors: loaded.wind_sectors,
          wind_max_kt: loaded.wind_max_kt,
          tide_phases: loaded.tide_phases,
          hour_min: loaded.hour_min,
          hour_max: loaded.hour_max,
        }
      : EMPTY);
  const configured = loaded ? !isEmpty({ ...EMPTY, ...loaded }) : false;

  const toggle = (
    key: "swell_sectors" | "wind_sectors" | "tide_phases",
    option: string,
  ) => {
    // On repart de `current`, c'est-à-dire du brouillon s'il existe et de
    // l'enregistré sinon : repartir de `EMPTY` effacerait tout au premier tap.
    const list = current[key] as string[];
    const next = list.includes(option)
      ? list.filter((item) => item !== option)
      : [...list, option];
    setDraft({ ...current, [key]: next } as Draft);
  };

  return (
    <section className="px-5 pt-5" aria-label="Tes critères pour ce spot">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 rounded-button border border-line bg-card px-4 text-left"
      >
        <span className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <IconSliders className="h-5 w-5 text-ink-2" />
          Tes critères
        </span>
        <span className="text-[13px] text-mute">
          {configured ? "posés" : "aucun"}
        </span>
      </button>

      {open ? (
        <div className="mt-3 rounded-card border border-line bg-card px-4 pb-4">
          <p className="pt-3 text-[13px] leading-snug text-ink-2">
            Décris quand ce spot marche. Tout est optionnel : ce que tu laisses
            sur « — » ne contraint rien. Quand un créneau des trois prochains
            jours correspond, Jour te le dit.
          </p>

          <ValuePicker
            label="Houle mini"
            unit="m"
            values={HEIGHTS}
            value={current.wave_height_min_m}
            onChange={(value) =>
              setDraft({ ...current, wave_height_min_m: value })
            }
          />
          <ValuePicker
            label="Houle maxi"
            unit="m — au-delà, c'est injouable"
            values={HEIGHTS}
            value={current.wave_height_max_m}
            onChange={(value) =>
              setDraft({ ...current, wave_height_max_m: value })
            }
          />
          <ValuePicker
            label="Période mini"
            unit="s"
            values={PERIODS}
            value={current.wave_period_min_s}
            onChange={(value) =>
              setDraft({ ...current, wave_period_min_s: value })
            }
            decimals={0}
          />

          <ChipGroup
            label="Houle de"
            hint="tous secteurs"
            options={SECTORS_8}
            selected={current.swell_sectors}
            render={(sector) => sector}
            onToggle={(sector: Sector8) => toggle("swell_sectors", sector)}
          />

          <ChipGroup
            label="Vent de"
            hint="tous secteurs"
            options={SECTORS_8}
            selected={current.wind_sectors}
            render={(sector) => sector}
            onToggle={(sector: Sector8) => toggle("wind_sectors", sector)}
          />
          <ValuePicker
            label="Vent maxi"
            unit="kt — au-delà, c'est injouable"
            values={WINDS}
            value={current.wind_max_kt}
            onChange={(value) => setDraft({ ...current, wind_max_kt: value })}
            decimals={0}
          />

          <ChipGroup
            label="Marée"
            hint="toutes phases"
            options={TIDE_PHASES}
            selected={current.tide_phases}
            render={(phase) => PHASE_LABELS[phase]}
            onToggle={(phase: TidePhase) => toggle("tide_phases", phase)}
          />

          <ValuePicker
            label="Pas avant"
            unit="h"
            values={HOURS}
            value={current.hour_min}
            onChange={(value) => setDraft({ ...current, hour_min: value })}
            decimals={0}
          />
          <ValuePicker
            label="Pas après"
            unit="h"
            values={HOURS}
            value={current.hour_max}
            onChange={(value) => setDraft({ ...current, hour_max: value })}
            decimals={0}
          />

          {save.error ? (
            <p className="pt-3 text-[13px] text-ink">
              {(save.error as Error).message}
            </p>
          ) : null}

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={() => save.mutate(current)}
              disabled={save.isPending}
              className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-50"
            >
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
            {configured ? (
              <button
                type="button"
                onClick={() => clear.mutate()}
                disabled={clear.isPending}
                aria-label="Effacer les critères"
                className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button border border-line bg-card text-ink-2 disabled:opacity-50"
              >
                <IconTrash className="h-5 w-5" />
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
