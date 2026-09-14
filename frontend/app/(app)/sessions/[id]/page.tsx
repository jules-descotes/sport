"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";

import { SegmentTimeline } from "@/components/session/SegmentTimeline";
import { WaveTypeChips } from "@/components/session/WaveTypeChips";
import { IconBack, IconPencil, IconTrash } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import {
  boardLength,
  clockLabel,
  coefficientLabel,
  compass,
  energyLabel,
  durationLabel,
  fullDayLabel,
  num,
  ratingLabel,
  scoreClass,
  shortDate,
} from "@/lib/format";
import type { SnapshotEntry, TideCoefficientDay, TideCoefficientMark } from "@/lib/types";

/**
 * Le coefficient de la pleine mer la plus proche d'un instant.
 *
 * Une journée en porte deux, et elles diffèrent de quelques points : celle du
 * matin n'est pas celle du soir. La fenêtre de six heures évite d'attraper
 * l'autre marée quand la session tombe entre les deux.
 */
function nearestCoefficient(
  days: TideCoefficientDay[],
  iso: string,
): TideCoefficientMark | null {
  const marks = days.flatMap((day) => day.marks);
  if (marks.length === 0) return null;
  const target = new Date(iso).getTime();
  const best = marks.reduce((closest, mark) =>
    Math.abs(new Date(mark.ts).getTime() - target) <
    Math.abs(new Date(closest.ts).getTime() - target)
      ? mark
      : closest,
  );
  return Math.abs(new Date(best.ts).getTime() - target) <= 6 * 3_600_000
    ? best
    : null;
}

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
    // Même grandeur et même constante que la ligne « Énergie » de l'écran
    // Surf — 0,49 × H² × T, calculée côté serveur pour qu'il n'y ait qu'un
    // seul chiffre possible (décidé le 13/09). Elle est dans la fenêtre parce
    // que c'est là qu'elle dit quelque chose : une houle qui monte de 8 à
    // 14 kJ en deux heures, c'est la session qui s'ouvre.
    { key: "wave_energy_kj", label: "Énergie", decimals: 1, unit: "kJ" },
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
        {ratingLabel(value)}
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

  const tides = useQuery({
    queryKey: ["tide-coefficients", "session", sessionId],
    queryFn: () =>
      api.tideCoefficients(data ? data.started_at.slice(0, 10) : undefined, 1),
    enabled: data !== undefined,
    staleTime: 24 * 60 * 60 * 1000,
  });

  const remove = useMutation({
    mutationFn: () => api.deleteSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session-journal"] });
      // La dépense du jour dépend de la durée **et** de la taille
      // des vagues déclarée : les deux viennent de changer.
      queryClient.invalidateQueries({ queryKey: ["expenditure"] });
      router.replace("/surf/sessions");
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

  // Le coefficient de la marée de la session. Il n'est pas figé dans le
  // snapshot : c'est une grandeur du **jour**, calculée à Brest, et elle se
  // relit à l'identique tant que le niveau marin de cette date est en base.
  // La figer en ferait une troisième copie à maintenir.
  const coefficient = nearestCoefficient(
    tides.data ?? [],
    data.started_at,
  );

  return (
    <main className="pb-10">
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <button
          type="button"
          onClick={() => router.push("/surf/sessions")}
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
        {/* Ce que les instruments ne mesurent pas — et que seul quelqu'un qui
            était à l'eau pouvait dire. Absent quand rien n'a été décrit :
            « non renseigné » n'est pas « moyen ». */}
        <WaveTypeChips value={data} className="mt-3" />
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
        <>
          <section className="flex gap-3 px-5 pb-1">
            <Note label="Conditions" value={data.rating_conditions} />
            <Note label="Ressenti" value={data.rating_personal} />
          </section>

          {/* Tout se corrige : date, spot, notes, planche, vagues, texte,
              photo (décidé le 13/09). Changer le spot ou l'heure refait le
              figeage des conditions, et conserve l'ancien. */}
          <section className="px-5 pt-4">
            <Link
              href={`/sessions/${data.id}/noter`}
              className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink"
            >
              <IconPencil className="h-5 w-5" />
              Modifier
            </Link>
          </section>
        </>
      )}

      {entry ? (
        <p className="tabular px-5 pt-4 text-[14px] text-ink-2">
          {num(entry.wave_height_m)} m · {num(entry.wave_period_s, 0)} s ·{" "}
          {compass(entry.wave_direction_deg)}
          {data.wave_energy_kj !== null
            ? ` · ${energyLabel(data.wave_energy_kj)} kJ`
            : ""}{" "}
          · vent {compass(entry.wind_direction_deg)}{" "}
          {num(entry.wind_speed_kt, 0)} kt · eau{" "}
          {num(entry.water_temperature_c, 0)} °C
          {coefficient ? (
            <>
              {" "}
              · coef.{" "}
              {coefficientLabel(coefficient.value, coefficient.approximate)}
            </>
          ) : null}
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

      {/* La frise horaire, quand elle existe. Juste avant les deux volets :
          elle raconte la session, ils décrivent la mer. */}
      <SegmentTimeline segments={data.segments} snapshot={snapshot} />

      {snapshot ? (
        <>
          <Window
            title="Constaté"
            hint={
              snapshot.observed_station
                ? `bouée ${snapshot.observed_station.name}${
                    snapshot.observed_station.distance_m !== null
                      ? `, ${Math.round(
                          snapshot.observed_station.distance_m / 1000,
                        )} km`
                      : ""
                  }`
                : "archive, à l'heure de la session"
            }
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
            {snapshot.observed_station ? (
              <>
                {" "}
                {snapshot.observed_station.hours} heure
                {snapshot.observed_station.hours > 1 ? "s" : ""} de ce volet
                {snapshot.observed_station.hours > 1
                  ? " viennent"
                  : " vient"}{" "}
                de la bouée {snapshot.observed_station.name} — une mesure, pas
                un modèle. La houle en vient ; le vent et la marée restent
                ceux de l&apos;archive, que la bouée ne mesure pas.
              </>
            ) : null}
          </p>
        </>
      ) : null}

      {/* Les versions précédentes du figeage. Elles n'apparaissent que si une
          correction en a produit — c'est-à-dire rarement, et c'est tant mieux.
          Quand elles existent, elles disent que la ligne d'apprentissage de
          cette session a changé, et pourquoi. */}
      {data.snapshot_history.length > 0 ? (
        <section className="px-5 pt-6">
          <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
            Versions précédentes
          </h2>
          <ul className="overflow-hidden rounded-card border border-line bg-card">
            {[...data.snapshot_history].reverse().map((version) => (
              <li
                key={version.replaced_at}
                className="border-b border-line px-4 py-2.5 last:border-0"
              >
                <p className="text-[14px] font-semibold text-ink">
                  {version.reason}
                </p>
                <p className="tabular mt-0.5 text-[12px] text-mute">
                  remplacée le {shortDate(version.replaced_at)} à{" "}
                  {clockLabel(version.replaced_at)} · figée pour le{" "}
                  {shortDate(version.started_at)}{" "}
                  {clockLabel(version.started_at)}
                </p>
              </li>
            ))}
          </ul>
          <p className="pt-2 text-[12px] leading-snug text-mute">
            Le figeage des conditions est la seule donnée du projet qu&apos;on
            ne peut pas reconstituer après coup : une correction ne l&apos;écrase
            jamais, elle l&apos;empile.
          </p>
        </section>
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
              {remove.isPending ? "Suppression…" : "Mettre à la corbeille"}
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
        <p className="pt-2 text-center text-[12px] text-mute">
          Corbeille de trente jours — restaurable depuis Surf › Sessions.
        </p>
      </section>
    </main>
  );
}
