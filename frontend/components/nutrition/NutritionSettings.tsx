"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconPlate } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { NutritionGoal } from "@/lib/types";

/**
 * **Ce que Mifflin-St Jeor a besoin de savoir**, et l'objectif.
 *
 * Quatre réglages, et ils ne se touchent qu'une fois : l'âge, le sexe, la
 * taille, et ce qu'on cherche à faire. Sans eux, la cible calorique se rabat
 * sur des valeurs par défaut plausibles **et le dit** — parce qu'une cible
 * refusée faute de taille laisserait l'écran vide, et qu'un écran vide ne se
 * remplit jamais.
 *
 * Le sexe est facultatif, et le rester : sans lui, la formule prend la moyenne
 * des deux constantes, soit 83 kcal d'écart au pire — du même ordre que ce que
 * la calibration par la balance rattrape en deux semaines.
 */

const GOALS: { value: NutritionGoal; label: string; hint: string }[] = [
  { value: "cut", label: "Sécher", hint: "−350 kcal" },
  { value: "maintain", label: "Maintenir", hint: "à l'équilibre" },
  { value: "bulk", label: "Prendre", hint: "+250 kcal" },
];

const SEXES: { value: string | null; label: string }[] = [
  { value: "male", label: "Homme" },
  { value: "female", label: "Femme" },
  { value: null, label: "Ne pas dire" },
];

/** Années de naissance proposées. On ne tape pas une date au clavier. */
const YEARS = Array.from({ length: 60 }, (_, index) => 2010 - index);

export function NutritionSettings() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const nutrition = useQuery({
    queryKey: ["nutrition-profile"],
    queryFn: api.nutritionProfile,
  });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });

  const save = useMutation({
    mutationFn: (data: Parameters<typeof api.updateNutritionProfile>[0]) =>
      api.updateNutritionProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["nutrition-profile"] });
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
    },
  });

  const profile = me.data?.profile;
  const goal = nutrition.data?.goal ?? "maintain";
  const birthYear = profile?.birth_date
    ? Number(profile.birth_date.slice(0, 4))
    : null;
  const height = profile?.height_m ?? null;

  return (
    <section className="px-5 pb-6" aria-label="Réglages nutrition">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 rounded-button border border-line bg-card px-4 text-left"
      >
        <span className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <IconPlate className="h-5 w-5 text-ink-2" />
          Nutrition
        </span>
        <span className="text-[13px] text-mute">
          {GOALS.find((entry) => entry.value === goal)?.label}
          {height ? ` · ${num(height, 2)} m` : " · à compléter"}
        </span>
      </button>

      {open ? (
        <div className="mt-3 rounded-card border border-line bg-card px-4 pb-4">
          <p className="pt-3 text-[13px] leading-snug text-ink-2">
            La cible calorique se calcule à partir de ces valeurs, puis se
            corrige toutes les deux à trois semaines sur ta balance. Tant
            qu&apos;elles manquent, elle est estimée — et elle le dit.
          </p>

          <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Objectif
          </p>
          <div className="flex gap-1.5">
            {GOALS.map((entry) => (
              <button
                key={entry.value}
                type="button"
                onClick={() => save.mutate({ goal: entry.value })}
                aria-pressed={goal === entry.value}
                className={`min-h-touch flex-1 rounded-button border px-2 text-[14px] font-semibold ${
                  goal === entry.value
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>

          <p className="pb-1.5 pt-4 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Année de naissance
          </p>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {YEARS.map((year) => (
              <button
                key={year}
                type="button"
                onClick={() => save.mutate({ birth_date: `${year}-01-01` })}
                aria-pressed={birthYear === year}
                className={`tabular min-h-touch shrink-0 rounded-pill border px-3.5 text-[15px] font-semibold ${
                  birthYear === year
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {year}
              </button>
            ))}
          </div>

          <p className="pb-1.5 pt-4 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Taille
          </p>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {Array.from({ length: 41 }, (_, index) => 1.5 + index * 0.01).map(
              (value) => {
                const rounded = Math.round(value * 100) / 100;
                const active =
                  height !== null && Math.abs(height - rounded) < 0.005;
                return (
                  <button
                    key={rounded}
                    type="button"
                    onClick={() => save.mutate({ height_m: rounded })}
                    aria-pressed={active}
                    className={`tabular min-h-touch shrink-0 rounded-pill border px-3 text-[15px] font-semibold ${
                      active
                        ? "border-accent bg-accent text-on-accent"
                        : "border-line bg-card text-ink-2"
                    }`}
                  >
                    {Math.round(rounded * 100)}
                  </button>
                );
              },
            )}
          </div>

          <p className="pb-1.5 pt-4 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Sexe{" "}
            <span className="font-normal normal-case">
              — facultatif, 83 kcal d&apos;écart au pire
            </span>
          </p>
          <div className="flex gap-1.5">
            {SEXES.map((entry) => (
              <button
                key={entry.label}
                type="button"
                onClick={() => save.mutate({ sex: entry.value })}
                aria-pressed={(profile?.sex ?? null) === entry.value}
                className={`min-h-touch flex-1 rounded-button border px-2 text-[14px] font-semibold ${
                  (profile?.sex ?? null) === entry.value
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>

          {nutrition.data && nutrition.data.calibration_kcal !== 0 ? (
            <p className="tabular pt-4 text-[12px] leading-snug text-mute">
              Calibration de la balance :{" "}
              {nutrition.data.calibration_kcal > 0 ? "+" : "−"}
              {num(Math.abs(nutrition.data.calibration_kcal), 0)} kcal
              {nutrition.data.calibrated_on
                ? `, le ${nutrition.data.calibrated_on}`
                : ""}
              .
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
