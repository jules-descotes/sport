"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";

import { Freshness, PullToRefresh } from "@/components/shell/Freshness";
import {
  COL_WIDTH,
  DESKTOP_COL_WIDTH,
  HourlyTable,
} from "@/components/surf/HourlyTable";
import { SlotDetailScreen } from "@/components/surf/SlotDetailScreen";
import { SpotPicker } from "@/components/surf/SpotPicker";
import { SurfTabs } from "@/components/surf/SurfTabs";
import { IconPlus, IconSearch, IconStar } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import { dayLabel, localDayKey } from "@/lib/format";
import { forecastKey } from "@/lib/forecast-cache";
import type { SpotForecast } from "@/lib/types";
import { useCachedForecast } from "@/lib/useCachedForecast";
import { useIsDesktop } from "@/lib/useMediaQuery";

/**
 * **Surf** — la prévision heure par heure, façon Windguru en plus moderne
 * (décidé le 13/09 après la première utilisation en ligne).
 *
 * Jour porte le résumé du spot favori, toutes les trois heures ; Surf porte
 * **le tableau complet** de n'importe quel spot du catalogue : cinq jours,
 * heure par heure, houle et énergie, vent et rafales, marée en courbe
 * continue, eau, note.
 *
 * **Le détail d'un créneau dépend de la place.** Sur téléphone il prend tout
 * l'écran — une seule information à la fois (`PROJET.md` §1, règle 9). Sur
 * desktop il s'ouvre en panneau latéral, le tableau restant à côté : c'est
 * justement là qu'on compare un créneau à son voisin, et faire disparaître la
 * matrice pour lire une de ses cases serait absurde sur 1 600 px.
 *
 * Ouvrir un spot ici reste **le seul geste qui déclenche une ingestion** : le
 * back récupère sa prévision si le cache serveur est vide ou dépasse trois
 * heures. Le cache client, lui, sert l'affichage sans attendre et ne
 * réinterroge qu'au-delà de deux heures.
 */

/** Cinq jours, toutes les heures : cent vingt colonnes de défilement. */
const DAYS = 5;
/** Pas de la prévision, en heures. Sert la clé de cache autant que l'appel. */
const STEP_HOURS = 1;

function SurfScreen() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const requestedSpot = searchParams.get("spot");
  const requestedTs = searchParams.get("ts");
  const isDesktop = useIsDesktop();

  const [chosenSlug, setChosenSlug] = useState<string | null>(requestedSpot);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedTs, setSelectedTs] = useState<string | null>(null);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  const favorites = useQuery({
    queryKey: ["spot-favorites"],
    queryFn: api.favoriteSpots,
  });

  // Faute de spot demandé, on ouvre sur le favori. Dérivé plutôt que posé dans
  // un effet : un état par défaut n'est pas un état.
  const slug = chosenSlug ?? favorites.data?.[0]?.slug ?? null;

  const setSlug = (next: string) => {
    setChosenSlug(next);
    setSelectedTs(null);
  };

  const forecast = useCachedForecast<SpotForecast>({
    // La forme demandée entre dans la clé : un tableau horaire et un résumé de
    // trois heures ne sont pas le même objet.
    cacheKey: slug === null ? null : forecastKey(slug, `${DAYS}d-${STEP_HOURS}h`),
    // `step_hours: 1` — le tableau est horaire. C'est deux fois plus de points
    // que l'ancienne grille de trois heures, et c'est tout l'objet de l'écran.
    queryKey: ["spot-hourly", slug],
    queryFn: () => api.spotForecast(slug as string, DAYS, STEP_HOURS),
    runTs: (data) => data.run_ts,
    enabled: slug !== null,
    keepPolling: (data) => data.refreshing,
  });

  /**
   * Les coefficients de marée, sur cinq jours.
   *
   * Une requête à part, et **sans spot** : le coefficient est national par
   * définition (calculé à Brest). L'embarquer dans la prévision du spot
   * laisserait croire le contraire, et le recalculerait pour chacun des
   * milliers de spots du catalogue.
   */
  const tides = useQuery({
    queryKey: ["tide-coefficients", DAYS],
    queryFn: () => api.tideCoefficients(undefined, DAYS),
    // Une marée ne change pas d'un quart d'heure à l'autre.
    staleTime: 6 * 60 * 60 * 1000,
  });

  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const homeSpotId = me.data?.profile?.home_spot_id ?? null;

  const setHome = useMutation({
    mutationFn: (spotId: number) => api.updateProfile({ home_spot_id: spotId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      queryClient.invalidateQueries({ queryKey: ["spot-favorites"] });
    },
  });

  const spot = forecast.data?.spot;
  // Mémoïsé : `?? []` fabriquerait un tableau neuf à chaque rendu, et l'effet
  // de défilement se redéclencherait sans fin.
  const points = useMemo(() => forecast.data?.points ?? [], [forecast.data]);
  const colWidth = isDesktop ? DESKTOP_COL_WIDTH : COL_WIDTH;

  /**
   * Positionne le tableau sur l'heure demandée.
   *
   * C'est ce qui donne son sens au tap depuis l'écran Jour : on touche le
   * créneau de 9 h dans le résumé, et Surf s'ouvre **sur** 9 h, pas au début
   * de la semaine. Le défilement est instantané — une animation sur cinq
   * mille pixels donnerait le mal de mer.
   */
  const scrolledTo = useRef<string | null>(null);
  useEffect(() => {
    if (!requestedTs || points.length === 0) return;
    if (scrolledTo.current === requestedTs) return;

    const index = points.findIndex((point) => point.ts === requestedTs);
    if (index < 0) return;

    scrolledTo.current = requestedTs;
    // La colonne des libellés est figée : elle ne compte pas dans le
    // défilement, et `index * colWidth` amène bien l'heure juste à sa droite.
    scroller.current
      ?.querySelector<HTMLDivElement>("[data-hourly-scroller]")
      ?.scrollTo({ left: index * colWidth, behavior: "instant" });
  }, [requestedTs, points, colWidth]);

  const scrollToDay = (dayKey: string) => {
    const index = points.findIndex((point) => localDayKey(point.ts) === dayKey);
    if (index < 0) return;
    scroller.current
      ?.querySelector<HTMLDivElement>("[data-hourly-scroller]")
      ?.scrollTo({ left: index * colWidth, behavior: "smooth" });
  };

  // Les cinq jours affichés, pour les pastilles de saut.
  const dayKeys: string[] = [];
  for (const point of points) {
    const key = localDayKey(point.ts);
    if (!dayKeys.includes(key)) dayKeys.push(key);
  }

  if (favorites.isPending && chosenSlug === null) {
    return (
      <main className="px-5 py-10">
        <p className="text-[14px] text-mute">Chargement…</p>
      </main>
    );
  }

  // Sur téléphone, le détail d'un créneau prend tout l'écran : une seule
  // information à la fois. Sur desktop il vit dans la colonne de droite, plus
  // bas — le tableau reste visible.
  if (selectedTs && slug && !isDesktop) {
    return (
      <SlotDetailScreen
        slug={slug}
        ts={selectedTs}
        onClose={() => setSelectedTs(null)}
      />
    );
  }

  if (pickerOpen || slug === null) {
    return (
      <main className="pb-6 pt-4">
        <header className="px-5 pb-4">
          <h1 className="font-display text-[32px] leading-none font-semibold uppercase tracking-wide text-ink">
            Surf
          </h1>
          <p className="mt-2 text-[14px] text-ink-2">
            La prévision de n&apos;importe quel spot du catalogue.
          </p>
        </header>
        <SurfTabs />
        <SpotPicker
          selectedId={spot?.id ?? null}
          onSelect={setSlug}
          onClose={() => setPickerOpen(false)}
        />
      </main>
    );
  }

  return (
    <main className="pb-6 pt-4" ref={scroller}>
      <PullToRefresh onRefresh={forecast.refresh} />

      <header className="flex items-start gap-3 px-5 pb-3">
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-[30px] leading-none font-semibold uppercase tracking-wide text-ink">
            {spot?.name ?? "Surf"}
          </h1>
          <p className="mt-1.5 text-[12px] text-mute">
            5 jours · heure par heure
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

      <SurfTabs />

      {forecast.isPending ? (
        <p className="px-5 text-[14px] text-mute">Lecture des prévisions…</p>
      ) : forecast.error ? (
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          {forecast.error instanceof ApiError && forecast.error.status === 404
            ? "Ce spot n'existe pas."
            : "Prévisions indisponibles. Réessaie quand le réseau revient."}
        </p>
      ) : (
        /* Desktop : le tableau prend la largeur, le détail se range à droite.
           Le panneau n'apparaît que lorsqu'un créneau est choisi — une colonne
           vide en permanence rétrécirait le tableau pour rien. */
        <div
          className={
            selectedTs
              ? "lg:grid lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start lg:gap-5 lg:px-5"
              : ""
          }
        >
          <div className={selectedTs ? "lg:min-w-0" : ""}>
            {/* Sauter à un jour : cent vingt colonnes, ça se traverse mal au
                doigt. Les pastilles sont le sommaire du tableau. */}
            {dayKeys.length > 1 ? (
              <nav
                aria-label="Aller à un jour"
                className={`flex gap-2 overflow-x-auto pb-2 ${
                  selectedTs ? "px-5 lg:px-0" : "px-5"
                }`}
              >
                {dayKeys.map((key) => {
                  const first = points.find(
                    (point) => localDayKey(point.ts) === key,
                  );
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => scrollToDay(key)}
                      className="min-h-touch shrink-0 rounded-pill border border-line bg-card px-4 text-[14px] font-semibold text-ink-2"
                    >
                      {first ? dayLabel(first.ts) : key}
                    </button>
                  );
                })}
              </nav>
            ) : null}

            <div className={selectedTs ? "px-5 lg:px-0" : "px-5"}>
              <HourlyTable
                points={points}
                sun={forecast.data?.sun ?? []}
                onshoreDirDeg={spot?.onshore_dir_deg ?? null}
                selectedTs={selectedTs}
                onSelect={setSelectedTs}
                secondaryOpen={secondaryOpen}
                onToggleSecondary={() => setSecondaryOpen((open) => !open)}
                colWidth={colWidth}
                coefficients={tides.data ?? []}
              />

              <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 text-[11px] text-mute">
                <li className="flex items-center gap-1.5">
                  Note
                  {[1, 2, 3, 4, 5].map((level) => (
                    <span
                      key={level}
                      className={`h-2.5 w-4 rounded-chip score-${level}`}
                      aria-hidden
                    />
                  ))}
                </li>
                <li className="flex items-center gap-1.5">
                  Intensité
                  {[1, 2, 3, 4, 5, 6].map((level) => (
                    <span
                      key={level}
                      className={`h-2.5 w-4 rounded-chip seq-${level}`}
                      aria-hidden
                    />
                  ))}
                </li>
                <li>Colonne pâle : nuit</li>
                <li>Touche une note pour le détail du créneau</li>
                {tides.data && tides.data.length > 0 ? (
                  <li>Touche la ligne marée pour le coefficient</li>
                ) : null}
              </ul>

              <Freshness
                className="pt-2"
                cachedAt={forecast.cachedAt}
                isFetching={forecast.isFetching}
                refreshing={forecast.data?.refreshing ?? false}
                onRefresh={forecast.refresh}
              />
            </div>

            <section className={`flex gap-3 pt-5 ${selectedTs ? "px-5 lg:px-0" : "px-5"}`}>
              <Link
                href={`/sessions/nouvelle${spot ? `?spot=${spot.id}` : ""}`}
                className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink"
              >
                <IconPlus className="h-5 w-5" />
                Ajouter une session
              </Link>
              {spot ? (
                <Link
                  href={`/surf/spots/${spot.slug}`}
                  className="flex min-h-touch items-center justify-center rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
                >
                  Fiche
                </Link>
              ) : null}
            </section>

            {spot ? (
              <section className={`pt-3 ${selectedTs ? "px-5 lg:px-0" : "px-5"}`}>
                <button
                  type="button"
                  onClick={() => setHome.mutate(spot.id)}
                  disabled={setHome.isPending || spot.id === homeSpotId}
                  className={`flex min-h-touch w-full items-center justify-center gap-2 rounded-button border px-4 text-[15px] font-semibold disabled:opacity-60 ${
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
              </section>
            ) : null}

            {spot?.id === homeSpotId ? (
              <p className={`pt-3 text-[12px] text-mute ${selectedTs ? "px-5 lg:px-0" : "px-5"}`}>
                Le spot favori est interrogé toutes les trois heures, même app
                fermée. C&apos;est son résumé qui s&apos;affiche sur Jour.
              </p>
            ) : null}
          </div>

          {/* Le détail, en panneau collant : on fait défiler le tableau sous
              lui sans le perdre de vue. */}
          {selectedTs && slug && isDesktop ? (
            <aside className="hidden lg:block lg:sticky lg:top-4">
              <SlotDetailScreen
                slug={slug}
                ts={selectedTs}
                onClose={() => setSelectedTs(null)}
                variant="panel"
              />
            </aside>
          ) : null}
        </div>
      )}
    </main>
  );
}

export default function SurfPage() {
  // `useSearchParams` impose une frontière de Suspense : sans elle, le rendu
  // statique de Next échoue au build.
  return (
    <Suspense
      fallback={<p className="px-5 py-10 text-[14px] text-mute">Chargement…</p>}
    >
      <SurfScreen />
    </Suspense>
  );
}
