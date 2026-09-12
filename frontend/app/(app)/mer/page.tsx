"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ForecastGrid } from "@/components/surf/ForecastGrid";
import { SpotPicker } from "@/components/surf/SpotPicker";
import { IconSearch, IconStar } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import {
  compass,
  fullDayLabel,
  num,
  scoreClass,
  tideLabel,
  windSideLabel,
} from "@/lib/format";
import type { ForecastPoint } from "@/lib/types";

/**
 * **Mer** — l'explorateur.
 *
 * Jour porte la prévision du spot favori ; Mer porte **la même grille pour
 * n'importe quel autre spot du catalogue**, par recherche, favoris ou position
 * (décidé le 12/09 au soir, cf. PROJET.md §11).
 *
 * Ouvrir un spot ici est **le seul geste qui déclenche une ingestion** : le
 * back récupère sa prévision si le cache est vide ou dépasse trois heures, et
 * sert la base au-delà de cinq secondes plutôt que de faire attendre.
 */

function SlotDetail({ point }: { point: ForecastPoint }) {
  const side = windSideLabel(point.wind_offshore_kt);
  const date = new Date(point.ts);

  return (
    <section className="px-5 pt-4" aria-live="polite">
      <article className="overflow-hidden rounded-card border border-line bg-card">
        <header className="flex items-center gap-4 px-4 pt-4">
          <span
            className={`tabular flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-card ${scoreClass(
              point.score_level,
            )}`}
          >
            <span className="font-display text-[24px] leading-none font-bold">
              {num(point.score, 1)}
            </span>
            <span className="text-[10px] font-semibold opacity-80">/ 5</span>
          </span>
          <div className="min-w-0">
            <p className="font-display text-[22px] leading-none font-semibold uppercase text-ink">
              {fullDayLabel(point.ts)} {date.getHours()} h
            </p>
            {point.reasons.length > 0 ? (
              <p className="mt-1.5 text-[13px] leading-snug text-mute">
                {point.reasons.join(" · ")}
              </p>
            ) : null}
          </div>
        </header>

        <dl className="tabular grid grid-cols-2 gap-px bg-line px-4 pb-4 pt-4">
          {[
            [
              "Houle",
              `${num(point.wave_height_m)} m · ${num(point.wave_period_s, 0)} s`,
            ],
            ["Direction", compass(point.wave_direction_deg)],
            [
              "Vent",
              `${compass(point.wind_direction_deg)} ${num(point.wind_speed_kt, 0)} kt${
                side ? ` ${side}` : ""
              }`,
            ],
            ["Rafales", `${num(point.wind_gust_kt, 0)} kt`],
            [
              "Marée",
              `${tideLabel(point.tide_rising)}${
                point.tide_range_m !== null
                  ? ` · ${num(point.tide_range_m)} m`
                  : ""
              }`,
            ],
            ["Eau", `${num(point.water_temperature_c, 0)} °C`],
          ].map(([label, value]) => (
            <div key={label} className="bg-card px-2 py-2">
              <dt className="text-[11px] uppercase tracking-wide text-mute">
                {label}
              </dt>
              <dd className="mt-0.5 text-[15px] font-semibold text-ink">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </article>
    </section>
  );
}

function MerScreen() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const requested = searchParams.get("spot");

  const [chosenSlug, setChosenSlug] = useState<string | null>(requested);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedTs, setSelectedTs] = useState<string | null>(null);

  const favorites = useQuery({
    queryKey: ["spot-favorites"],
    queryFn: api.favoriteSpots,
  });

  // Faute de spot demandé, on ouvre sur le favori — c'est celui qu'on regarde
  // le plus souvent, et il est en tête de la liste des favoris. Dérivé plutôt
  // que posé dans un effet : un `setState` dans un effet déclenche un second
  // rendu pour rien, et l'état par défaut n'est pas un état.
  const slug = chosenSlug ?? favorites.data?.[0]?.slug ?? null;

  const setSlug = (next: string) => {
    setChosenSlug(next);
    setSelectedTs(null);
  };

  const forecast = useQuery({
    // `step_hours: 3` : quarante points au lieu de cent vingt.
    queryKey: ["spot-grid", slug],
    queryFn: () => api.spotForecast(slug as string, 5, 3),
    enabled: slug !== null,
    refetchInterval: (query) => (query.state.data?.refreshing ? 6_000 : false),
  });

  const setHome = useMutation({
    mutationFn: (spotId: number) => api.updateProfile({ home_spot_id: spotId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      queryClient.invalidateQueries({ queryKey: ["spot-favorites"] });
    },
  });

  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const homeSpotId = me.data?.profile?.home_spot_id ?? null;

  const spot = forecast.data?.spot;
  const points = forecast.data?.points ?? [];
  const selected = points.find((point) => point.ts === selectedTs) ?? null;

  if (favorites.isPending && chosenSlug === null) {
    return (
      <main className="px-5 py-10">
        <p className="text-[14px] text-mute">Chargement…</p>
      </main>
    );
  }

  if (pickerOpen || slug === null) {
    return (
      <main className="pb-6 pt-4">
        <header className="px-5 pb-4">
          <h1 className="font-display text-[32px] leading-none font-semibold uppercase tracking-wide text-ink">
            Mer
          </h1>
          <p className="mt-2 text-[14px] text-ink-2">
            La prévision de n&apos;importe quel spot du catalogue.
          </p>
        </header>
        <SpotPicker
          selectedId={spot?.id ?? null}
          onSelect={setSlug}
          onClose={() => setPickerOpen(false)}
        />
      </main>
    );
  }

  return (
    <main className="pb-6 pt-4">
      <header className="flex items-start gap-3 px-5 pb-3">
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-[30px] leading-none font-semibold uppercase tracking-wide text-ink">
            {spot?.name ?? "Mer"}
          </h1>
          <p className="mt-1.5 text-[12px] text-mute">
            5 jours · toutes les 3 h
            {forecast.data?.run_ts
              ? ` · prévision de ${new Date(forecast.data.run_ts).getHours()} h`
              : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          aria-label="Changer de spot"
          className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button border border-line bg-card text-ink-2"
        >
          <IconSearch className="h-5 w-5" />
        </button>
      </header>

      {forecast.isPending ? (
        <p className="px-5 text-[14px] text-mute">Lecture des prévisions…</p>
      ) : forecast.error ? (
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          {forecast.error instanceof ApiError && forecast.error.status === 404
            ? "Ce spot n'existe pas."
            : "Prévisions indisponibles. Réessaie quand le réseau revient."}
        </p>
      ) : (
        <>
          <div className="px-5">
            <ForecastGrid
              points={points}
              selectedTs={selectedTs}
              onSelect={setSelectedTs}
            />
            <ul className="flex items-center gap-1.5 pt-2 text-[11px] text-mute">
              <li>1</li>
              {[1, 2, 3, 4, 5].map((level) => (
                <li
                  key={level}
                  className={`h-2.5 w-5 rounded-chip ${scoreClass(level)}`}
                  aria-hidden
                />
              ))}
              <li>5</li>
              <li className="ml-auto">Cellule éteinte : nuit</li>
            </ul>
          </div>

          {selected ? (
            <SlotDetail point={selected} />
          ) : (
            <p className="px-5 pt-3 text-[13px] text-mute">
              Touche une cellule pour le détail du créneau.
            </p>
          )}

          {spot ? (
            <section className="flex gap-3 px-5 pt-5">
              <button
                type="button"
                onClick={() => setHome.mutate(spot.id)}
                disabled={setHome.isPending || spot.id === homeSpotId}
                className={`flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button border px-4 text-[15px] font-semibold disabled:opacity-60 ${
                  spot.id === homeSpotId
                    ? "border-line bg-card text-ink-2"
                    : "border-accent bg-accent text-on-accent"
                }`}
              >
                <IconStar className="h-5 w-5" filled={spot.id === homeSpotId} />
                {spot.id === homeSpotId
                  ? "Spot favori"
                  : "Définir comme favori"}
              </button>
              <Link
                href={`/surf/spots/${spot.slug}`}
                className="flex min-h-touch items-center justify-center rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
              >
                Fiche
              </Link>
            </section>
          ) : null}

          {spot?.id === homeSpotId ? (
            <p className="px-5 pt-3 text-[12px] text-mute">
              Le spot favori est interrogé toutes les trois heures, même app
              fermée. C&apos;est sa prévision qui s&apos;affiche sur Jour.
            </p>
          ) : null}

          {forecast.data?.refreshing ? (
            <p className="px-5 pt-3 text-[12px] text-mute">
              Prévision en cours de récupération…
            </p>
          ) : null}
        </>
      )}
    </main>
  );
}

export default function MerPage() {
  // `useSearchParams` impose une frontière de Suspense : sans elle, le rendu
  // statique de Next échoue au build.
  return (
    <Suspense
      fallback={<p className="px-5 py-10 text-[14px] text-mute">Chargement…</p>}
    >
      <MerScreen />
    </Suspense>
  );
}
