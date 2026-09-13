"use client";

import Link from "next/link";

import { waveTypeLabels } from "@/components/session/WaveTypeChips";
import { IconChevronRight } from "@/components/ui/Icons";
import {
  clockLabel,
  durationLabel,
  energyLabel,
  ratingLabel,
  scoreClass,
  shortDate,
} from "@/lib/format";
import type { SurfSession } from "@/lib/types";

/**
 * Une ligne d'historique — traitement **liste dense** (V2 de l'exploration).
 *
 * C'est la deuxième vue dense du produit, après la grille de l'écran Surf, et
 * elle l'est pour la même raison : on ne lit pas un historique une information
 * à la fois, on le balaie pour retrouver une journée. Date, spot, durée, les
 * **deux** notes, la planche — tout tient sur une ligne, et les deux notes
 * gardent les couleurs de l'échelle, les mêmes que sur Jour et sur Surf.
 *
 * Les deux notes côte à côte ne sont pas un détail d'affichage : c'est le
 * seul endroit du produit où l'on voit d'un coup d'œil les jours où la mer
 * était bonne et pas la forme, et l'inverse.
 */
function Note({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <span className="flex h-8 w-8 items-center justify-center rounded-chip border border-line bg-soft text-[13px] text-mute">
        —
      </span>
    );
  }
  return (
    <span
      className={`tabular flex h-8 w-8 items-center justify-center rounded-chip font-display text-[15px] font-bold leading-none ${scoreClass(
        value,
      )}`}
    >
      {ratingLabel(value)}
    </span>
  );
}

export function SessionRow({ session }: { session: SurfSession }) {
  const pending = session.status === "to_rate";

  return (
    <li className="border-b border-line last:border-0">
      <Link
        href={
          pending ? `/sessions/${session.id}/noter` : `/sessions/${session.id}`
        }
        className="flex min-h-touch items-center gap-3 px-4 py-2.5"
      >
        <span className="w-[52px] shrink-0">
          <span className="tabular block text-[14px] font-semibold text-ink">
            {shortDate(session.started_at)}
          </span>
          <span className="tabular block text-[12px] text-mute">
            {clockLabel(session.started_at)}
          </span>
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-semibold text-ink">
            {session.spot?.name ?? "Spot inconnu"}
          </span>
          <span className="block truncate text-[12px] text-mute">
            {durationLabel(session.duration_min)}
            {session.gear ? ` · ${session.gear.name}` : ""}
            {session.wave_count !== null ? ` · ${session.wave_count} vagues` : ""}
            {/* Le type de vagues, quand il a été décrit. Il est sur cette
                ligne parce que l'historique se filtre dessus : une liste
                filtrée sur « creuses » doit montrer pourquoi chaque ligne y
                est. */}
            {waveTypeLabels(session).length > 0
              ? ` · ${waveTypeLabels(session).join(", ").toLowerCase()}`
              : ""}
          </span>
        </span>

        {/* L'énergie de la houle, en colonne (décidé le 13/09). Même grandeur
            et même constante que l'écran Surf. Elle est ici et pas la hauteur
            seule parce que c'est elle qui sépare deux sessions d'un mètre :
            à 7 s et à 15 s, ce n'est pas la même mer. Masquée sous 360 px,
            où la ligne est déjà pleine. */}
        <span className="tabular hidden w-[52px] shrink-0 text-right min-[360px]:block">
          <span className="block text-[14px] font-semibold text-ink-2">
            {energyLabel(session.wave_energy_kj)}
          </span>
          <span className="block text-[11px] text-mute">kJ</span>
        </span>

        {pending ? (
          <span className="shrink-0 rounded-pill border border-accent px-2.5 py-1 text-[12px] font-semibold text-accent">
            À noter
          </span>
        ) : (
          <span className="flex shrink-0 gap-1.5">
            <Note value={session.rating_conditions} />
            <Note value={session.rating_personal} />
          </span>
        )}

        <IconChevronRight className="h-4 w-4 shrink-0 text-mute" />
      </Link>
    </li>
  );
}
