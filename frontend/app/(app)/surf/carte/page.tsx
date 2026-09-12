"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { TileMap } from "@/components/surf/TileMap";
import { api } from "@/lib/api";
import { distanceLabel } from "@/lib/format";
import { useGeolocation } from "@/lib/useGeolocation";

/**
 * Carte des spots proches. Appui long = ajout d'un spot.
 *
 * La couverture OSM est inégale : là où elle est vide, le spot s'ajoute en
 * deux taps depuis la carte, et l'import mensuel n'y touchera jamais
 * (`source='user'`).
 */
export default function CartePage() {
  const geolocation = useGeolocation();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [pending, setPending] = useState<{ lat: number; lon: number } | null>(
    null,
  );
  const [name, setName] = useState("");

  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: api.preferences,
  });

  const center = geolocation.position ??
    (preferences.data?.home_lat !== null &&
    preferences.data?.home_lat !== undefined &&
    preferences.data?.home_lon !== null &&
    preferences.data?.home_lon !== undefined
      ? { lat: preferences.data.home_lat, lon: preferences.data.home_lon }
      : null);

  const nearby = useQuery({
    queryKey: ["spots-nearby", center],
    queryFn: () =>
      api.spotsNearby({ lat: center!.lat, lon: center!.lon, radius_km: 60 }),
    enabled: center !== null,
  });

  const create = useMutation({
    mutationFn: (data: { name: string; lat: number; lon: number }) =>
      api.createSpot(data),
    onSuccess: (spot) => {
      setPending(null);
      setName("");
      queryClient.invalidateQueries({ queryKey: ["spots-nearby"] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      router.push(`/surf/spots/${spot.slug}`);
    },
  });

  if (geolocation.status === "pending" || preferences.isPending) {
    return (
      <>
        <ScreenHeader title="Carte" />
        <p className="px-5 text-[14px] text-mute">Localisation…</p>
      </>
    );
  }

  if (!center) {
    return (
      <>
        <ScreenHeader title="Carte" />
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Aucune position connue. Choisis un domicile dans le profil, ou
          autorise la géolocalisation.
        </p>
      </>
    );
  }

  const favorites = new Set(preferences.data?.favorite_spot_ids ?? []);

  return (
    <>
      <ScreenHeader
        title="Carte"
        subtitle="Appui long sur la carte pour ajouter un spot."
      />

      <div className="px-5">
        <TileMap
          center={center}
          zoom={11}
          className="h-[52vh] min-h-[300px]"
          markers={(nearby.data ?? []).map((spot) => ({
            id: spot.id,
            lat: spot.lat,
            lon: spot.lon,
            label: `${spot.name} — ${distanceLabel(spot.distance_km)}`,
            highlight: favorites.has(spot.id),
            onSelect: () => router.push(`/surf/spots/${spot.slug}`),
          }))}
          onLongPress={(position) => setPending(position)}
        />
      </div>

      {pending ? (
        <section className="px-5 pt-4">
          <div className="rounded-card border border-line bg-card px-4 py-4">
            <h2 className="font-display text-[18px] font-semibold uppercase text-ink">
              Nouveau spot
            </h2>
            <p className="tabular mt-1 text-[12px] text-mute">
              {pending.lat.toFixed(4)}, {pending.lon.toFixed(4)}
            </p>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Nom du spot"
              aria-label="Nom du spot"
              className="mt-3 min-h-touch w-full rounded-button border border-line bg-soft px-4 text-[16px] text-ink"
            />
            <div className="mt-3 flex gap-3">
              <button
                type="button"
                onClick={() => {
                  setPending(null);
                  setName("");
                }}
                className="min-h-touch flex-1 rounded-button border border-line bg-soft px-4 text-[15px] font-semibold text-ink-2"
              >
                Annuler
              </button>
              <button
                type="button"
                disabled={!name.trim() || create.isPending}
                onClick={() =>
                  create.mutate({ name: name.trim(), ...pending })
                }
                className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-50"
              >
                {create.isPending ? "Ajout…" : "Ajouter"}
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <p className="px-5 pt-4 text-[12px] text-mute">
        {nearby.data?.length ?? 0} spot(s) dans un rayon de 60 km.
      </p>
    </>
  );
}
