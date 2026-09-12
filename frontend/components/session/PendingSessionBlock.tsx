"use client";

import Link from "next/link";

import { IconChevronRight, IconClock } from "@/components/ui/Icons";
import { clockLabel, durationLabel, fullDayLabel, shortDate } from "@/lib/format";
import type { SurfSession } from "@/lib/types";

/**
 * « Tu es allé à l'eau. Note-la. » — le bloc qui passe devant tout le reste.
 *
 * Rendu **plein cadre** (V4), pleine largeur, sur l'accent : c'est le seul
 * endroit de l'app où l'accent couvre une surface entière, et c'est justifié —
 * il n'y a qu'une action possible à cet instant, et elle est la plus rentable
 * du produit. Une session enregistrée mais non notée ne vaut rien pour le
 * modèle : c'est une ligne sans étiquette.
 *
 * Il passe **au-dessus du bloc de mer**, qui reprend sa place une fois la
 * notation faite. L'ordre de l'écran Jour est celui de la journée telle qu'on
 * la vit : à 11 h, ce qui compte n'est plus la prévision du matin, c'est la
 * session qu'on vient de finir.
 */
export function PendingSessionBlock({ session }: { session: SurfSession }) {
  return (
    <section className="px-5">
      <Link
        href={`/sessions/${session.id}/noter`}
        className="flex items-center gap-4 rounded-card bg-accent px-5 py-5 text-on-accent"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] opacity-75">
            Session à noter
          </span>
          <span className="mt-1.5 block truncate font-display text-[32px] font-bold leading-none uppercase tracking-tight">
            {session.spot?.name ?? "Spot inconnu"}
          </span>
          <span className="tabular mt-2 flex items-center gap-1.5 text-[14px] opacity-85">
            <IconClock className="h-4 w-4 shrink-0" />
            {fullDayLabel(session.started_at)} {clockLabel(session.started_at)}
            {" · "}
            {durationLabel(session.duration_min)}
          </span>
        </span>
        <IconChevronRight className="h-6 w-6 shrink-0 opacity-75" />
      </Link>
    </section>
  );
}

/**
 * La session du jour une fois notée — en pied d'écran, avec ses deux notes.
 *
 * Sobre, et c'est voulu : la journée est faite, l'information est un rappel,
 * pas une action. Elle reste cliquable pour revoir la fenêtre de conditions.
 */
export function DoneSessionRow({ session }: { session: SurfSession }) {
  return (
    <Link
      href={`/sessions/${session.id}`}
      className="flex items-center gap-3 rounded-card border border-line bg-card px-4 py-3"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-mute">
          À l&apos;eau · {shortDate(session.started_at)}
        </span>
        <span className="mt-0.5 block truncate text-[15px] font-semibold text-ink">
          {session.spot?.name ?? "Spot inconnu"}
        </span>
        <span className="tabular block text-[12px] text-mute">
          {clockLabel(session.started_at)} ·{" "}
          {durationLabel(session.duration_min)}
          {session.gear ? ` · ${session.gear.name}` : ""}
        </span>
      </span>

      {/* Les deux notes, jamais une seule — et toujours dans le même ordre :
          la mer d'abord, la forme du jour ensuite. */}
      <span className="flex shrink-0 gap-1.5">
        {[session.rating_conditions, session.rating_personal].map(
          (value, index) => (
            <span
              key={index}
              className={`tabular flex h-9 w-9 items-center justify-center rounded-chip font-display text-[18px] font-bold leading-none ${
                value === null
                  ? "border border-line bg-soft text-mute"
                  : `score-${value}`
              }`}
            >
              {value ?? "—"}
            </span>
          ),
        )}
      </span>
    </Link>
  );
}
