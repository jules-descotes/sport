"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { IconChevronDown } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { durationLabel } from "@/lib/format";

/**
 * **La dépense estimée du jour**, sur l'écran Jour (décidé le 13/09, n° 4).
 *
 * Une ligne, un chiffre, et le mot « estimation » — pas « 617 kcal ». Rien de
 * ce qui compose ce chiffre n'est mesuré : le MET vient du compendium
 * d'activités physiques pour « surf, général », la durée est arrondie au quart
 * d'heure, et la taille des vagues est un souvenir. Il est utile parce qu'il
 * dit si la journée a coûté deux cents ou sept cents kilocalories ; il serait
 * malhonnête au kcal près.
 *
 * **Le détail s'ouvre au tap**, et il n'est pas de la décoration : « 620 kcal »
 * ne dit pas si c'est la session de trois heures ou la séance de renfo qui
 * pèse, donc ne dit pas quoi rectifier quand le chiffre paraît faux. Un
 * chiffre qu'on ne peut pas rectifier, on cesse de le lire.
 *
 * Rien ne s'affiche quand la journée n'a rien coûté. Une ligne « 0 kcal » sur
 * l'écran du matin serait un reproche, et ce produit n'en fait pas.
 */
export function DayExpenditure() {
  const [open, setOpen] = useState(false);

  const { data } = useQuery({
    queryKey: ["expenditure"],
    queryFn: () => api.expenditure(),
  });

  if (!data || data.total_kcal <= 0) return null;

  return (
    <section className="px-5" aria-label="Dépense estimée">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 rounded-card border border-line bg-card px-4 py-2.5 text-left"
      >
        <span className="min-w-0">
          <span className="block text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
            Dépense estimée
          </span>
          <span className="tabular block font-display text-[24px] font-bold leading-none text-ink">
            ≈ {data.total_kcal} kcal
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="tabular text-[13px] text-mute">
            {durationLabel(data.surf_min + data.workout_min)}
          </span>
          <IconChevronDown
            className={`h-5 w-5 text-mute transition-transform ${
              open ? "rotate-180" : ""
            }`}
          />
        </span>
      </button>

      {open ? (
        <div className="mt-2 rounded-card border border-line bg-soft px-4 py-3">
          <ul className="flex flex-col gap-2">
            {data.items.map((item, index) => (
              <li
                key={`${item.kind}-${index}`}
                className="flex items-baseline justify-between gap-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-[15px] font-semibold text-ink">
                    {item.label}
                  </span>
                  <span className="tabular block text-[12px] text-mute">
                    {durationLabel(item.minutes)}
                    {item.detail ? ` · ${item.detail}` : ""} · {item.met} MET
                  </span>
                </span>
                <span className="tabular shrink-0 text-[15px] font-semibold text-ink-2">
                  ≈ {item.kcal}
                </span>
              </li>
            ))}
          </ul>

          <p className="pt-3 text-[12px] leading-snug text-mute">
            Estimation, pas une mesure : dépense <strong>en plus</strong> de ne
            rien faire, sur {data.weight_kg} kg
            {data.weight_estimated ? " (poids par défaut — pèse-toi)" : ""}. La
            balance corrige le reste toutes les deux à trois semaines, et
            c&apos;est elle qui a le dernier mot sur la cible.
          </p>
        </div>
      ) : null}
    </section>
  );
}
