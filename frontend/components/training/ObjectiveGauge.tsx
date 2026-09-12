"use client";

import { IconPlus } from "@/components/ui/Icons";
import { num } from "@/lib/format";
import type { Objective } from "@/lib/types";

/**
 * Une jauge d'objectif : **départ, aujourd'hui, cible**.
 *
 * Trois nombres et un trait. Le curseur marque où l'on en est entre le départ
 * et la cible — pas un pourcentage abstrait, la position réelle sur le chemin.
 *
 * **Tant qu'il n'y a aucune mesure, la jauge est vide et le dit.** Un
 * remplissage inventé se lirait comme un relevé, et c'est exactement ce que la
 * table de mesures existe pour empêcher. Le bouton devient alors la seule
 * chose visible : il n'y a rien d'autre à faire que mesurer.
 *
 * L'objectif le plus en retard passe en accent — sur l'écran Training, ce seul
 * remplissage dit tout sans une ligne de texte (V4 de l'exploration).
 */

/** « 2:10 » pour une durée, « −6 cm » pour une distance. */
export function objectiveValueLabel(
  value: number | null,
  unit: string,
): string {
  if (value === null) return "—";
  if (unit === "s") {
    const total = Math.round(value);
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return minutes > 0
      ? `${minutes}:${String(seconds).padStart(2, "0")}`
      : `${seconds} s`;
  }
  if (unit === "deg") return `${num(value, 0)}°`;
  return `${num(value, value % 1 === 0 ? 0 : 1)} ${unit}`;
}

export function ObjectiveGauge({
  objective,
  behind,
  onMeasure,
}: {
  objective: Objective;
  /** Vrai pour l'objectif le plus en retard — le seul en accent. */
  behind: boolean;
  onMeasure: () => void;
}) {
  const ratio = objective.ratio;
  const measured = objective.current_value !== null;

  return (
    <article
      className={`rounded-card border bg-card px-5 py-4 ${
        behind ? "border-accent" : "border-line"
      }`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-[22px] font-semibold uppercase leading-none text-ink">
          {objective.name}
        </h3>
        <p
          className={`tabular shrink-0 font-display text-[26px] font-bold leading-none ${
            measured ? (behind ? "text-accent" : "text-ink") : "text-mute"
          }`}
        >
          {objectiveValueLabel(objective.current_value, objective.unit)}
        </p>
      </div>

      <p className="mt-1 text-[13px] leading-snug text-mute">
        {objective.measure}
      </p>

      {/* Le trait : départ à gauche, cible à droite, curseur où on en est. */}
      <div
        className="mt-3 h-2.5 overflow-hidden rounded-pill border border-line bg-soft"
        role="img"
        aria-label={
          ratio === null
            ? `${objective.name} : pas encore mesuré`
            : `${objective.name} : ${Math.round(ratio * 100)} % du chemin`
        }
      >
        {ratio !== null ? (
          <div
            className={`h-full ${behind ? "bg-accent" : "bg-seq-4"}`}
            style={{ width: `${Math.max(2, Math.round(ratio * 100))}%` }}
          />
        ) : null}
      </div>

      <dl className="tabular mt-2 flex items-baseline justify-between gap-3 text-[12px] text-mute">
        <div className="flex gap-1.5">
          <dt>Départ</dt>
          <dd className="font-semibold text-ink-2">
            {objectiveValueLabel(objective.start_value, objective.unit)}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt>Cible</dt>
          <dd className="font-semibold text-ink-2">
            {objectiveValueLabel(objective.target_value, objective.unit)}
          </dd>
        </div>
      </dl>

      {objective.needs_measurement ? (
        <button
          type="button"
          onClick={onMeasure}
          className="mt-3 flex min-h-touch w-full items-center justify-center gap-2 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent"
        >
          <IconPlus className="h-5 w-5" />
          {measured
            ? `Mesurer — ${objective.measure_every_days} jours sont passés`
            : "Première mesure"}
        </button>
      ) : (
        <button
          type="button"
          onClick={onMeasure}
          className="mt-3 flex min-h-touch w-full items-center justify-center rounded-button border border-line bg-card px-4 text-[14px] font-semibold text-ink-2"
        >
          Mesurer
          {objective.last_measured_on ? (
            <span className="ml-1.5 text-mute">
              · dernière le{" "}
              {new Date(objective.last_measured_on).toLocaleDateString("fr-FR", {
                day: "numeric",
                month: "short",
              })}
            </span>
          ) : null}
        </button>
      )}
    </article>
  );
}
