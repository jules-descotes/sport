"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";

import { IconBack, IconTrash } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import {
  boardLength,
  clockLabel,
  compass,
  durationLabel,
  fullDayLabel,
  num,
  scoreClass,
  shortDate,
} from "@/lib/format";
import type { SnapshotEntry } from "@/lib/types";

/**
 * **Détail d'une session** — ce qui a été noté, et ce qu'il y avait dans l'eau.
 *
 * L'écran existe surtout pour montrer le `conditions_snapshot`, et il le
 * montre tel qu'il est stocké : une **fenêtre** de trois heures, en deux
 * volets qui ne se mélangent jamais.
 *
 * - `observed` — ce qui s'est passé, remonté de l'archive à l'enregistrement.
 *   C'est là-dessus que le modèle de goût s'entraîne (`PROJET.md` §7.3) ;
 * - `forecast` — ce qui était annoncé **avant** d'aller à l'eau, et seulement
 *   ce qui l'était : les runs émis après le début sont écartés, sans quoi on
 *   servirait au modèle une information qu'il n'avait pas (§7.1).
 *
 * Les afficher côte à côte n'est pas de la décoration : c'est la seule façon
 * de voir, session après session, de combien le fournisseur se trompe — et
 * c'est ce qui justifiera un jour une barre d'incertitude sur les recos.
 */

const ROWS: { key: keyof SnapshotEntry; label: string; decimals: number; unit: string }[] =
  [
    { key: "wave_height_m", label: "Houle", decimals: 1, unit: "m" },
    { key: "wave_period_s", label: "Période", decimals: 0, unit: "s" },
    { key: "wind_speed_kt", label: "Vent", decimals: 0, unit: "kt" },
    { key: "wind_gust_kt", label: "Rafales", decimals: 0, unit: "kt" },
    { key: "sea_level_m", label: "Niveau", decimals: 2, unit: "m" },
  ];

function Note({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="pb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-mute">
        {label}
      </p>
      <p
        className={`tabular flex h-[76px] items-center justify-center rounded-card font-display text-[42px] font-bold leading-none ${
          value === null
            ? "border border-line bg-soft text-mute"
            : scoreClass(value)
        }`}
      >
        {value ?? "—"}
      </p>
    </div>
  );
}

/**
 * Un volet de la fenêtre, en matrice : trois colonnes fixes, T−2 h / T−1 h /
 * T0. Une heure manquante s'éteint au lieu de disparaître — une colonne en
 * moins décalerait toute la lecture, exactement comme sur la grille de Surf.
 */
function Window({
  title,
  hint,
  entries,
}: {
  title: string;
  hint: string;
  entries: SnapshotEntry[];
}) {
  const byOffset = new Map(entries.map((entry) => [entry.offset_h, entry]));

  return (
    <section className="px-5 pt-5">
      <div className="flex items-baseline justify-between gap-3 pb-2">
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {title}
        </h2>
        <span className="text-[12px] text-mute">{hint}</span>
      </div>

      {entries.length === 0 ? (
        <p className="rounded-card border border-line bg-card px-4 py-3 text-[14px] text-ink-2">
          {title === "Constaté"
            ? "L'archive n'a pas répondu à l'enregistrement. Elle sera rattrapée à la prochaine notation."
            : "Aucune prévision n'avait été captée pour ce spot avant la session."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-card border border-line bg-card">
          <div className="tabular grid grid-cols-[1fr_repeat(3,minmax(0,1fr))] border-b border-line bg-soft">
            <span />
            {[-2, -1, 0].map((offset) => (
              <span
                key={offset}
                className="px-2 py-2 text-center text-[12px] font-semibold text-mute"
              >
                {offset === 0 ? "T0" : `T${offset} h`}
              </span>
            ))}
          </div>

          {ROWS.map((row) => (
            <div
              key={String(row.key)}
              className="tabular grid grid-cols-[1fr_repeat(3,minmax(0,1fr))] border-b border-line last:border-0"
            >
              <span className="px-3 py-2 text-[12px] uppercase tracking-wide text-mute">
                {row.label}
              </span>
              {[-2, -1, 0].map((offset) => {
                const value = byOffset.get(offset)?.[row.key] as number | null;
                return (
                  <span
                    key={offset}
                    className={`px-2 py-2 text-center text-[15px] font-semibold ${
                      value === null || value === undefined
                        ? "text-mute"
                        : "text-ink"
                    }`}
                  >
                    {value === null || value === undefined
                      ? "—"
                      : num(value, row.decimals)}
                    {value !== null && value !== undefined ? (
                      <span className="text-[11px] font-normal text-mute">
                        {" "}
                        {row.unit}
                      </span>
                    ) : null}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const sessionId = Number(params.id);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const { data, isPending, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.session(sessionId),
    enabled: Number.isFinite(sessionId),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session-journal"] });
      router.replace("/sessions");
    },
  });

  if (isPending) {
    return (
      <main className="px-5 py-10">
        <p className="text-[14px] text-mute">Chargement…</p>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="px-5 py-10 text-center">
        <p className="text-[16px] text-ink">Session introuvable.</p>
      </main>
    );
  }

  const snapshot = data.conditions_snapshot;
  const entry = snapshot?.observed.find((item) => item.offset_h === 0);

  return (
    <main className="pb-10">
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <button
          type="button"
          onClick={() => router.push("/sessions")}
          aria-label="Retour à l'historique"
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {fullDayLabel(data.started_at)} {shortDate(data.started_at)}
        </p>
      </header>

      <section className="px-5 pb-5">
        <h1 className="truncate font-display text-[32px] font-bold leading-none uppercase tracking-tight text-ink">
          {data.spot?.name ?? "Spot inconnu"}
        </h1>
        <p className="tabular mt-2 text-[14px] text-ink-2">
          {clockLabel(data.started_at)} · {durationLabel(data.duration_min)}
          {data.gear
            ? ` · ${data.gear.name}${
                data.gear.length_m ? ` ${boardLength(data.gear.length_m)}` : ""
              }`
            : ""}
          {data.wave_count !== null ? ` · ${data.wave_count} vagues` : ""}
        </p>
      </section>

      {data.status === "to_rate" ? (
        <section className="px-5 pb-5">
          <Link
            href={`/sessions/${data.id}/noter`}
            className="flex min-h-[56px] items-center justify-center rounded-button bg-accent px-5 text-[17px] font-semibold text-on-accent"
          >
            Noter cette session
          </Link>
        </section>
      ) : (
        <section className="flex gap-3 px-5 pb-1">
          <Note label="Conditions" value={data.rating_conditions} />
          <Note label="Ressenti" value={data.rating_personal} />
        </section>
      )}

      {entry ? (
        <p className="tabular px-5 pt-4 text-[14px] text-ink-2">
          {num(entry.wave_height_m)} m · {num(entry.wave_period_s, 0)} s ·{" "}
          {compass(entry.wave_direction_deg)} · vent{" "}
          {compass(entry.wind_direction_deg)} {num(entry.wind_speed_kt, 0)} kt ·
          eau {num(entry.water_temperature_c, 0)} °C
        </p>
      ) : null}

      {data.notes ? (
        <section className="px-5 pt-5">
          <p className="rounded-card border border-line bg-card px-4 py-3 text-[15px] leading-snug text-ink-2">
            {data.notes}
          </p>
        </section>
      ) : null}

      {data.photo_url ? (
        <section className="px-5 pt-5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={data.photo_url}
            alt="Photo de la session"
            className="w-full rounded-card border border-line"
          />
        </section>
      ) : null}

      {snapshot ? (
        <>
          <Window
            title="Constaté"
            hint="archive, à l'heure de la session"
            entries={snapshot.observed}
          />
          <Window
            title="Prévu avant"
            hint="dernier run émis avant le début"
            entries={snapshot.forecast}
          />
          <p className="px-5 pt-3 text-[12px] leading-snug text-mute">
            Fenêtre figée à l&apos;enregistrement — {snapshot.model}
            {snapshot.model_version ? ` ${snapshot.model_version}` : ""}. Les
            deux volets restent séparés : une prévision et une mesure ne sont
            pas la même grandeur.
          </p>
        </>
      ) : null}

      <section className="px-5 pt-8">
        {confirming ? (
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-touch flex-1 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
            >
              Annuler
            </button>
            <button
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
              className="min-h-touch flex-1 rounded-button border border-line bg-soft px-4 text-[15px] font-semibold text-ink disabled:opacity-50"
            >
              {remove.isPending ? "Suppression…" : "Confirmer"}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[14px] font-semibold text-mute"
          >
            <IconTrash className="h-4 w-4" />
            Supprimer la session
          </button>
        )}
      </section>
    </main>
  );
}
