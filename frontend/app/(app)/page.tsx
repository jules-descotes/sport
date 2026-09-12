"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DailyLogSwipe } from "@/components/surf/DailyLogSwipe";
import { VerdictCard } from "@/components/surf/VerdictCard";
import { IconGrid, IconPin, IconUser } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { distanceLabel, num, scoreClass } from "@/lib/format";
import { useGeolocation } from "@/lib/useGeolocation";

/**
 * « Je vais à l'eau, oui ou non, et où ? »
 *
 * Une seule question, une seule réponse en très grand. Tout le reste — le
 * comparateur, la carte, le profil — est à un tap.
 */
export default function SurfHomePage() {
  const geolocation = useGeolocation();

  const { data, isPending, error, isFetching } = useQuery({
    // La position fait partie de la clé : changer de coin recharge la reco.
    queryKey: ["recommend", geolocation.position],
    queryFn: () => api.recommend(geolocation.position),
    // On attend la géoloc, mais pas éternellement : dès qu'elle est tranchée
    // (acceptée, refusée ou indisponible), on interroge le back, qui se rabat
    // sur le domicile si besoin.
    enabled: geolocation.status !== "pending",
    // Le back complète parfois en arrière-plan : on retente une fois.
    refetchInterval: (query) =>
      query.state.data?.refreshing.length ? 6_000 : false,
  });

  if (geolocation.status === "pending" || isPending) {
    return (
      <main className="flex min-h-[60vh] flex-col items-center justify-center gap-2 px-5">
        <p className="font-display text-[22px] text-ink-2">Je regarde la mer…</p>
        <p className="text-[13px] text-mute">
          {geolocation.status === "pending"
            ? "Localisation en cours"
            : "Prévisions en cours de lecture"}
        </p>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="px-5 py-10 text-center">
        <p className="text-[16px] text-ink">Prévisions indisponibles.</p>
        <p className="mt-2 text-[14px] text-mute">
          Réessaie quand le réseau revient.
        </p>
      </main>
    );
  }

  const others = data.spots.filter(
    (item) => item.spot.id !== data.headline_spot?.id,
  );

  return (
    <main className="flex flex-col gap-4 pb-6 pt-4">
      {geolocation.status === "denied" && data.position_source === "home" ? (
        <p className="px-5 text-[12px] text-mute">
          Géolocalisation refusée — prévisions autour de ton domicile.
        </p>
      ) : null}

      <VerdictCard data={data} />

      <DailyLogSwipe />

      {/* Les autres spots proches, du meilleur au moins bon. Une ligne par
          spot : c'est une liste de décision, pas un tableau de bord.

          Le titre précise l'horizon, et ce n'est pas du zèle : le verdict
          porte sur la prochaine fenêtre de jour, cette liste sur les cinq
          jours. Sans la mention, un 4,4 affiché sous un verdict à 3,0 n'a
          aucun sens. */}
      {others.length > 0 ? (
        <section className="px-5">
          <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Autour de toi · meilleur créneau sur 5 jours
          </h2>
          <ul className="overflow-hidden rounded-card border border-line bg-card">
            {others.map((item) => (
              <li key={item.spot.id} className="border-b border-line last:border-0">
                <Link
                  href={`/surf/spots/${item.spot.slug}`}
                  className="flex min-h-touch items-center gap-3 px-4 py-3"
                >
                  <span
                    className={`tabular flex h-9 w-9 shrink-0 items-center justify-center rounded-cell text-[14px] font-semibold ${scoreClass(
                      item.best?.level,
                    )}`}
                  >
                    {item.best ? num(item.best.score, 1) : "—"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold text-ink">
                      {item.spot.name}
                    </span>
                    <span className="block truncate text-[12px] text-mute">
                      {item.best?.line ?? "Pas encore de prévision"}
                    </span>
                  </span>
                  <span className="shrink-0 text-[12px] text-mute">
                    {distanceLabel(item.distance_km)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <nav className="grid grid-cols-3 gap-3 px-5" aria-label="Raccourcis surf">
        {[
          { href: "/surf/comparateur", label: "Comparer", Icon: IconGrid },
          { href: "/surf/carte", label: "Carte", Icon: IconPin },
          { href: "/profil", label: "Profil", Icon: IconUser },
        ].map(({ href, label, Icon }) => (
          <Link
            key={href}
            href={href}
            className="flex min-h-touch flex-col items-center justify-center gap-1 rounded-card border border-line bg-card py-3 text-[13px] font-semibold text-ink-2"
          >
            <Icon className="h-5 w-5" />
            {label}
          </Link>
        ))}
      </nav>

      {isFetching || data.refreshing.length > 0 ? (
        <p className="px-5 text-[12px] text-mute">
          Mise à jour des prévisions en cours…
        </p>
      ) : null}
    </main>
  );
}
