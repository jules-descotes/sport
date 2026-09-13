"use client";

import { useState } from "react";

import { IconChevronDown } from "@/components/ui/Icons";
import { DEFAULT_THRESHOLDS, legendRows } from "@/lib/quality-colors";
import type { Thresholds } from "@/lib/types";

/**
 * La légende du tableau horaire — **repliée**.
 *
 * Depuis le 13/09 les cellules sont teintées par **qualité pour Jules** et non
 * par intensité brute. C'est plus utile et c'est moins évident : sans légende,
 * une cellule pâle peut vouloir dire « petit » ou « sous ton minimum », et
 * personne ne devine laquelle.
 *
 * Repliée, parce que la légende sert **une fois** — le jour où l'on change ses
 * seuils — et que le tableau se lit tous les matins. Dépliée en permanence,
 * elle occuperait trois lignes sous la seule vue qu'on ouvre à bout de bras.
 *
 * Les paliers affichés sont ceux de **ses** seuils, pas des valeurs
 * d'exemple : une légende qui dirait « 8 s » quand il a réglé 10 s serait pire
 * qu'aucune légende.
 */
export function QualityLegend({
  thresholds,
  className = "",
}: {
  thresholds?: Thresholds | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const rows = legendRows(thresholds ?? DEFAULT_THRESHOLDS);

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch items-center gap-1.5 text-[12px] font-semibold text-mute"
      >
        Comment lire les couleurs
        <IconChevronDown
          className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <div className="flex flex-col gap-2 pb-1 pt-1">
          {rows.map((row) => (
            <div key={row.axis} className="flex flex-wrap items-center gap-2">
              <span className="w-[62px] shrink-0 text-[12px] font-semibold text-ink-2">
                {row.axis}
              </span>
              {row.entries.map((entry) => (
                <span
                  key={`${row.axis}-${entry.label}`}
                  className="flex items-center gap-1.5 text-[11px] text-mute"
                >
                  <span
                    className={`h-3 w-5 rounded-chip border border-line ${entry.className}`}
                    aria-hidden
                  />
                  {entry.label}
                </span>
              ))}
            </div>
          ))}

          <p className="max-w-[560px] text-[11px] leading-snug text-mute">
            Les couleurs disent <strong>ce qui est bon pour toi</strong>, pas ce
            qui est gros : une houle de 3 m est grosse, ce qui n&apos;est pas la
            même chose. Le vent est le seul axe inversé — moins il y en a, mieux
            c&apos;est. La ligne du bas garde l&apos;échelle de note 1 → 5, et
            c&apos;est la seule. Réglable dans Profil → Tes seuils.
          </p>
        </div>
      ) : null}
    </div>
  );
}
