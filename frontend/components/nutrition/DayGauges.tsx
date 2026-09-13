"use client";

import { num } from "@/lib/format";
import type { MacroTotals, NutritionTarget } from "@/lib/types";

/**
 * **La cible du jour, et où on en est.** Sobre, et jamais rouge.
 *
 * C'est une règle de ton, pas de couleur : un journal alimentaire qui gronde
 * est un journal qu'on cesse d'ouvrir, et un journal fermé ne recalibre rien.
 * Le dépassement se voit — la barre passe la ligne — mais il ne s'accuse pas.
 * On mesure, on n'évalue pas.
 *
 * Deux jauges seulement : **les calories et les protéines**. Les glucides et
 * les lipides sont donnés en chiffres, sans barre. C'est délibéré : les
 * protéines sont la seule macro qu'on tient vraiment (elles se fixent au poids
 * de corps), les glucides sont la variable d'ajustement, et quatre jauges
 * feraient un tableau de bord d'avion pour un geste de trois secondes.
 */
interface DayGaugesProps {
  target: NutritionTarget;
  totals: MacroTotals;
  /** Rendu compact pour l'écran Jour, plein pour l'écran Nutrition. */
  compact?: boolean;
}

function Bar({
  label,
  value,
  target,
  unit,
  decimals = 0,
}: {
  label: string;
  value: number;
  target: number;
  unit: string;
  decimals?: number;
}) {
  const ratio = target > 0 ? value / target : 0;
  // La barre se remplit jusqu'à la cible ; au-delà, un second trait déborde
  // par-dessus. Écrêter à 100 % cacherait le dépassement, l'étirer ferait
  // rétrécir la partie utile.
  const filled = Math.min(1, ratio);
  const over = Math.max(0, Math.min(0.35, ratio - 1));

  return (
    <div className="min-w-0 flex-1">
      <div className="flex items-baseline justify-between gap-2 pb-1">
        <span className="text-[12px] font-semibold uppercase tracking-wide text-mute">
          {label}
        </span>
        <span className="tabular text-[13px] text-ink-2">
          <span className="text-[15px] font-semibold text-ink">
            {num(value, decimals)}
          </span>
          {" / "}
          {num(target, decimals)} {unit}
        </span>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-pill bg-soft">
        <span
          className="absolute inset-y-0 left-0 rounded-pill bg-accent"
          style={{ width: `${filled * 100}%` }}
        />
        {over > 0 ? (
          <span
            className="absolute inset-y-0 right-0 rounded-pill bg-ink-2 opacity-50"
            style={{ width: `${over * 100}%` }}
          />
        ) : null}
      </div>
    </div>
  );
}

export function DayGauges({ target, totals, compact = false }: DayGaugesProps) {
  const remaining = target.kcal - totals.kcal;

  return (
    <div>
      {!compact ? (
        <div className="flex items-end gap-3 pb-4">
          <p className="tabular font-display text-[52px] font-bold leading-none text-ink">
            {num(Math.max(0, remaining), 0)}
          </p>
          <p className="pb-1 text-[14px] leading-snug text-ink-2">
            kcal
            <br />
            {remaining >= 0 ? "restantes" : "au-delà"}
          </p>
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <Bar
          label="Calories"
          value={totals.kcal}
          target={target.kcal}
          unit="kcal"
        />
        <Bar
          label="Protéines"
          value={totals.protein_g}
          target={target.protein_g}
          unit="g"
        />
      </div>

      <p className="tabular pt-2 text-[12px] text-mute">
        Glucides {num(totals.carb_g, 0)} / {target.carb_g} g · Lipides{" "}
        {num(totals.fat_g, 0)} / {target.fat_g} g
        {target.protein_g_per_kg
          ? ` · ${num(target.protein_g_per_kg, 1)} g/kg de protéines visés`
          : ""}
      </p>
    </div>
  );
}

/**
 * D'où vient la cible — le détail, replié.
 *
 * Une cible qui monte de 400 kcal sans dire pourquoi n'est pas croyable, et une
 * cible pas croyable ne se suit pas. Trois lignes suffisent : le métabolisme,
 * ce que la journée a coûté, et ce que la balance a corrigé.
 */
export function TargetBreakdown({ target }: { target: NutritionTarget }) {
  const rows: [string, string][] = [
    ["Base", `${num(target.base_kcal, 0)} kcal`],
  ];

  if (target.expenditure.surf_min > 0) {
    rows.push([
      `Surf ${target.expenditure.surf_min} min`,
      `+${num(target.expenditure.surf_kcal, 0)} kcal`,
    ]);
  }
  if (target.expenditure.workout_min > 0) {
    rows.push([
      `Séance ${target.expenditure.workout_min} min`,
      `+${num(target.expenditure.workout_kcal, 0)} kcal`,
    ]);
  }
  if (target.goal_kcal !== 0) {
    rows.push([
      "Objectif",
      `${target.goal_kcal > 0 ? "+" : "−"}${num(Math.abs(target.goal_kcal), 0)} kcal`,
    ]);
  }
  if (target.calibration_kcal !== 0) {
    rows.push([
      "Calibration balance",
      `${target.calibration_kcal > 0 ? "+" : "−"}${num(
        Math.abs(target.calibration_kcal),
        0,
      )} kcal`,
    ]);
  }

  return (
    <div className="pt-3">
      <dl className="tabular">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="flex items-baseline justify-between gap-3 border-t border-line py-1.5"
          >
            <dt className="text-[12px] uppercase tracking-wide text-mute">
              {label}
            </dt>
            <dd className="text-[14px] font-medium text-ink-2">{value}</dd>
          </div>
        ))}
      </dl>

      {target.estimated ? (
        <p className="pt-2 text-[12px] leading-snug text-mute">
          {target.reasons.join(" · ")}. Complète ton profil et pèse-toi pour
          que la cible devienne la tienne.
        </p>
      ) : null}
    </div>
  );
}
