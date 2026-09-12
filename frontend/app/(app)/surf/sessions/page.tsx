"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { SessionRow } from "@/components/session/SessionRow";
import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { SurfTabs } from "@/components/surf/SurfTabs";
import {
  IconCloudOff,
  IconFilter,
  IconPlus,
  IconRestore,
  IconTrash,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { clockLabel, scoreClass, shortDate } from "@/lib/format";
import { useOfflineQueue } from "@/lib/useOfflineQueue";

/**
 * **Historique** — liste dense, la plus récente en haut, sous Surf.
 *
 * C'est la deuxième vue dense du produit, après le tableau horaire, et elle
 * l'est pour la même raison : on ne lit pas un historique une information à la
 * fois, on le balaie pour retrouver une journée.
 *
 * Trois filtres, et trois seulement : **spot**, **mois**, **note**. Ce sont
 * les trois façons dont on cherche une session — « c'était à la Gravière »,
 * « c'était en mars », « les bonnes ». L'analyse fine est le lot 6, et c'est
 * elle qui dira « tes meilleures sessions : houle 1,2–1,8 m, période 11–14 s,
 * marée montante » (`PROJET.md` §10.8).
 *
 * Le filtrage par spot et par note est fait **par le serveur** ; le mois est
 * traduit en bornes `since` / `until`. Rien n'est filtré côté client : à 240
 * sessions par an, la liste dépassera vite la page, et un filtre qui ne
 * s'applique qu'à la page visible est un filtre qui ment.
 */
const PAGE_SIZE = 60;

/** Les douze derniers mois, du plus récent au plus ancien. */
function lastMonths(count = 12): { key: string; label: string; date: Date }[] {
  const now = new Date();
  const months: { key: string; label: string; date: Date }[] = [];
  for (let index = 0; index < count; index += 1) {
    const date = new Date(now.getFullYear(), now.getMonth() - index, 1);
    months.push({
      key: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`,
      label: date.toLocaleDateString("fr-FR", {
        month: "short",
        year: index === 0 || date.getFullYear() !== now.getFullYear() ? "2-digit" : undefined,
      }),
      date,
    });
  }
  return months;
}

/** Première seconde du mois, au format `YYYY-MM-DD` attendu par l'API. */
function isoDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(
    2,
    "0",
  )}-${String(date.getDate()).padStart(2, "0")}`;
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`min-h-touch shrink-0 rounded-pill border px-4 text-[14px] font-semibold ${
        active
          ? "border-accent bg-accent text-on-accent"
          : "border-line bg-card text-ink-2"
      }`}
    >
      {children}
    </button>
  );
}

export default function SessionsPage() {
  const offline = useOfflineQueue();
  const queryClient = useQueryClient();

  const [filtersOpen, setFiltersOpen] = useState(false);
  const [spotId, setSpotId] = useState<number | null>(null);
  const [month, setMonth] = useState<string | null>(null);
  const [minRating, setMinRating] = useState<number | null>(null);
  const [trashOpen, setTrashOpen] = useState(false);

  const months = useMemo(() => lastMonths(), []);
  const chosenMonth = months.find((entry) => entry.key === month) ?? null;

  const { data, isPending, error } = useQuery({
    queryKey: ["sessions", "history", spotId, month, minRating],
    queryFn: () =>
      api.sessions({
        limit: PAGE_SIZE,
        ...(spotId !== null ? { spot_id: spotId } : {}),
        ...(minRating !== null ? { min_rating: minRating } : {}),
        ...(chosenMonth
          ? {
              since: isoDay(chosenMonth.date),
              until: isoDay(
                new Date(
                  chosenMonth.date.getFullYear(),
                  chosenMonth.date.getMonth() + 1,
                  0,
                ),
              ),
            }
          : {}),
      }),
  });

  const trash = useQuery({
    queryKey: ["sessions", "trash"],
    queryFn: api.trashedSessions,
    enabled: trashOpen,
  });

  const restore = useMutation({
    mutationFn: (id: number) => api.restoreSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session-journal"] });
    },
  });

  // Les spots proposés au filtre sont ceux qui **portent des sessions**, pas
  // le catalogue mondial : filtrer sur un spot où l'on n'est jamais allé n'a
  // aucun sens, et la liste doit tenir sans défilement infini.
  const all = useQuery({
    queryKey: ["sessions", "spots"],
    queryFn: () => api.sessions({ limit: 200 }),
    enabled: filtersOpen,
  });

  const spots = useMemo(() => {
    const seen = new Map<number, string>();
    for (const session of all.data ?? []) {
      if (session.spot) seen.set(session.spot.id, session.spot.name);
    }
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [all.data]);

  const pending = (data ?? []).filter(
    (session) => session.status === "to_rate",
  ).length;
  const filtered = spotId !== null || month !== null || minRating !== null;

  return (
    <main className="pb-8">
      <ScreenHeader
        title="Sessions"
        subtitle={
          data && data.length > 0
            ? `${data.length} ${filtered ? "trouvée(s)" : "enregistrée(s)"}${
                pending ? ` · ${pending} à noter` : ""
              }`
            : undefined
        }
      />

      <SurfTabs />

      <section className="flex gap-2 px-5 pb-3">
        <Link
          href="/sessions/nouvelle"
          className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent"
        >
          <IconPlus className="h-5 w-5" />
          Ajouter une session
        </Link>
        <button
          type="button"
          onClick={() => setFiltersOpen((open) => !open)}
          aria-expanded={filtersOpen}
          aria-label="Filtrer l'historique"
          className={`flex h-touch w-touch shrink-0 items-center justify-center rounded-button border ${
            filtered
              ? "border-accent bg-card text-accent"
              : "border-line bg-card text-ink-2"
          }`}
        >
          <IconFilter className="h-5 w-5" />
        </button>
      </section>

      {filtersOpen ? (
        <section
          className="flex flex-col gap-3 px-5 pb-4"
          aria-label="Filtres de l'historique"
        >
          <div>
            <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-wide text-mute">
              Spot
            </p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              <Chip active={spotId === null} onClick={() => setSpotId(null)}>
                Tous
              </Chip>
              {spots.map(([id, name]) => (
                <Chip
                  key={id}
                  active={spotId === id}
                  onClick={() => setSpotId(spotId === id ? null : id)}
                >
                  {name}
                </Chip>
              ))}
            </div>
          </div>

          <div>
            <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-wide text-mute">
              Mois
            </p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              <Chip active={month === null} onClick={() => setMonth(null)}>
                Tous
              </Chip>
              {months.map((entry) => (
                <Chip
                  key={entry.key}
                  active={month === entry.key}
                  onClick={() => setMonth(month === entry.key ? null : entry.key)}
                >
                  {entry.label}
                </Chip>
              ))}
            </div>
          </div>

          <div>
            <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-wide text-mute">
              Note de conditions, au moins
            </p>
            <div className="flex gap-2">
              <Chip
                active={minRating === null}
                onClick={() => setMinRating(null)}
              >
                Toutes
              </Chip>
              {[2, 3, 4, 5].map((level) => (
                <button
                  key={level}
                  type="button"
                  onClick={() =>
                    setMinRating(minRating === level ? null : level)
                  }
                  aria-pressed={minRating === level}
                  aria-label={`Au moins ${level} sur 5`}
                  className={`tabular flex h-touch min-w-touch items-center justify-center rounded-cell font-display text-[20px] font-bold ${scoreClass(
                    level,
                  )} ${minRating === level ? "ring-2 ring-ink" : "opacity-70"}`}
                >
                  {level}+
                </button>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {offline.pending > 0 ? (
        <p className="flex items-center gap-2 px-5 pb-3 text-[13px] text-mute">
          <IconCloudOff className="h-4 w-4 shrink-0" />
          {offline.pending} notation(s) en attente d&apos;envoi
        </p>
      ) : null}

      {isPending ? (
        <p className="px-5 text-[14px] text-mute">Lecture de l&apos;historique…</p>
      ) : error ? (
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Historique indisponible. Réessaie quand le réseau revient.
        </p>
      ) : data && data.length > 0 ? (
        <ul className="mx-5 overflow-hidden rounded-card border border-line bg-card">
          {data.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </ul>
      ) : filtered ? (
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Aucune session avec ces filtres.
        </p>
      ) : (
        <section className="px-5">
          <article className="rounded-card border border-line bg-card px-5 py-6">
            <h2 className="font-display text-[24px] font-semibold leading-none uppercase text-ink">
              Aucune session
            </h2>
            <p className="mt-3 text-[15px] leading-snug text-ink-2">
              La plus rapide s&apos;enregistre en sortant de l&apos;eau, depuis
              le raccourci iPhone — il se met en place une fois, dans le profil.
              Une session ancienne se saisit ici, avec sa date.
            </p>
            <Link
              href="/profil/jetons"
              className="mt-4 flex min-h-touch items-center justify-center rounded-button border border-line bg-soft px-4 text-[16px] font-semibold text-ink"
            >
              Mettre en place le raccourci
            </Link>
          </article>
        </section>
      )}

      {/* La corbeille, repliée : on n'y va qu'après une erreur, et une
          corbeille visible en permanence invite à supprimer. */}
      <section className="px-5 pt-6">
        <button
          type="button"
          onClick={() => setTrashOpen((open) => !open)}
          aria-expanded={trashOpen}
          className="flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[14px] font-semibold text-mute"
        >
          <IconTrash className="h-4 w-4" />
          Corbeille
        </button>

        {trashOpen ? (
          trash.isPending ? (
            <p className="pt-3 text-[14px] text-mute">Lecture…</p>
          ) : (trash.data ?? []).length === 0 ? (
            <p className="pt-3 text-[13px] leading-snug text-mute">
              Rien en corbeille. Une session supprimée y reste trente jours
              avant d&apos;être détruite.
            </p>
          ) : (
            <ul className="mt-3 overflow-hidden rounded-card border border-line bg-card">
              {(trash.data ?? []).map((session) => (
                <li
                  key={session.id}
                  className="flex items-center gap-3 border-b border-line px-4 py-2.5 last:border-0"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold text-ink">
                      {session.spot?.name ?? "Spot inconnu"}
                    </span>
                    <span className="tabular block text-[12px] text-mute">
                      {shortDate(session.started_at)}{" "}
                      {clockLabel(session.started_at)}
                      {session.deleted_at
                        ? ` · supprimée le ${shortDate(session.deleted_at)}`
                        : ""}
                    </span>
                  </span>
                  <button
                    type="button"
                    disabled={restore.isPending}
                    onClick={() => restore.mutate(session.id)}
                    className="flex min-h-touch shrink-0 items-center gap-1.5 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink disabled:opacity-50"
                  >
                    <IconRestore className="h-4 w-4" />
                    Restaurer
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>
    </main>
  );
}
