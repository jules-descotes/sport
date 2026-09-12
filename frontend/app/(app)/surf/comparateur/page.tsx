"use client";

import { useQuery } from "@tanstack/react-query";

import { Comparator } from "@/components/surf/Comparator";
import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { api } from "@/lib/api";
import { useGeolocation } from "@/lib/useGeolocation";

/**
 * La seule vue dense de l'application, et elle scrolle horizontalement.
 * Elle réutilise la réponse de `/recommend` — même clé de cache que l'accueil,
 * donc zéro appel supplémentaire quand on y arrive depuis le verdict.
 */
export default function ComparateurPage() {
  const geolocation = useGeolocation();

  const { data, isPending, error } = useQuery({
    queryKey: ["recommend", geolocation.position],
    queryFn: () => api.recommend(geolocation.position),
    enabled: geolocation.status !== "pending",
  });

  return (
    <>
      <ScreenHeader title="Comparateur" subtitle="Heures × spots, sur 5 jours." />

      {isPending || geolocation.status === "pending" ? (
        <p className="px-5 text-[14px] text-mute">Lecture des prévisions…</p>
      ) : error || !data ? (
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Prévisions indisponibles. Réessaie quand le réseau revient.
        </p>
      ) : (
        <Comparator data={data} />
      )}
    </>
  );
}
