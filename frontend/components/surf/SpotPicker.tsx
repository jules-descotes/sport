"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { IconCrosshair, IconSearch, IconStar } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { distanceLabel } from "@/lib/format";
import type { SpotHit } from "@/lib/types";
import { useGeolocation } from "@/lib/useGeolocation";

/**
 * Le sélecteur de spot de l'écran Surf : recherche par nom, favoris, autour de
 * moi.
 *
 * **Aucun de ces trois chemins n'ingère quoi que ce soit.** Chercher
 * « Lafitenia » ne coûte pas trois appels Open-Meteo ; la prévision se récupère
 * quand on ouvre le spot, et pas avant. C'est la règle « zéro appel tant que
 * personne ne regarde », prise spot par spot.
 *
 * Le clavier n'apparaît que pour la recherche, qui est le seul endroit de
 * l'app où l'on ne peut pas faire autrement — on ne va pas dérouler un
 * catalogue mondial en molette.
 */

interface SpotPickerProps {
  selectedId: number | null;
  /** Le `slug` sert la navigation ; le `hit` évite un aller-retour de plus
   *  quand l'appelant a besoin de l'identifiant — c'est le cas des écrans de
   *  session, qui stockent un `spot_id`. */
  onSelect: (slug: string, hit: SpotHit) => void;
  onClose: () => void;
  /** Titre au-dessus de la liste. Par défaut, celui de l'écran Surf. */
  heading?: string;
}

function Row({
  hit,
  onSelect,
  selected,
}: {
  hit: SpotHit;
  onSelect: (slug: string, hit: SpotHit) => void;
  selected: boolean;
}) {
  return (
    <li className="border-b border-line last:border-0">
      <button
        type="button"
        onClick={() => onSelect(hit.slug, hit)}
        className="flex min-h-touch w-full items-center gap-3 px-4 py-2.5 text-left"
      >
        {hit.is_home ? (
          <IconStar className="h-4 w-4 shrink-0 text-accent" filled />
        ) : null}
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-[15px] font-semibold ${
              selected ? "text-accent" : "text-ink"
            }`}
          >
            {hit.name}
          </span>
          <span className="block truncate text-[12px] text-mute">
            {[hit.region, hit.country_code].filter(Boolean).join(" · ") ||
              "Catalogue OpenStreetMap"}
          </span>
        </span>
        {hit.distance_km !== null ? (
          <span className="tabular shrink-0 text-[12px] text-mute">
            {distanceLabel(hit.distance_km)}
          </span>
        ) : null}
      </button>
    </li>
  );
}

export function SpotPicker({ selectedId, onSelect, onClose }: SpotPickerProps) {
  const geolocation = useGeolocation();
  const [term, setTerm] = useState("");
  const [nearbyOpen, setNearbyOpen] = useState(false);

  const query = term.trim();

  const favorites = useQuery({
    queryKey: ["spot-favorites"],
    queryFn: api.favoriteSpots,
  });

  const search = useQuery({
    queryKey: ["spot-search", query, geolocation.position],
    queryFn: () => api.searchSpots(query, geolocation.position),
    // Deux caractères au minimum : une lettre renverrait la moitié du catalogue.
    enabled: query.length >= 2,
  });

  const nearby = useQuery({
    queryKey: ["spots-nearby", geolocation.position],
    queryFn: () =>
      api.spotsNearby({
        lat: geolocation.position!.lat,
        lon: geolocation.position!.lon,
        radius_km: 40,
        }),
    enabled: nearbyOpen && geolocation.position != null,
  });

  const results: SpotHit[] | null =
    query.length >= 2
      ? (search.data ?? null)
      : nearbyOpen && nearby.data
        ? nearby.data.map((spot) => ({ ...spot, is_home: spot.is_home }))
        : (favorites.data ?? null);

  const heading =
    query.length >= 2
      ? "Résultats"
      : nearbyOpen
        ? "Autour de moi"
        : "Mes spots";

  return (
    <section className="px-5" aria-label="Choisir un spot">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-mute" />
          <input
            type="search"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="Chercher un spot"
            aria-label="Chercher un spot par son nom"
            autoComplete="off"
            className="min-h-touch w-full rounded-button border border-line bg-card pl-10 pr-3 text-[16px] text-ink placeholder:text-mute"
          />
        </div>
        <button
          type="button"
          onClick={() => {
            setTerm("");
            setNearbyOpen((open) => !open);
          }}
          aria-pressed={nearbyOpen}
          aria-label="Spots autour de moi"
          disabled={geolocation.position == null}
          className={`flex h-touch w-touch shrink-0 items-center justify-center rounded-button border disabled:opacity-40 ${
            nearbyOpen
              ? "border-accent bg-accent text-on-accent"
              : "border-line bg-card text-ink-2"
          }`}
        >
          <IconCrosshair className="h-5 w-5" />
        </button>
      </div>

      <h2 className="pb-2 pt-4 text-[12px] font-semibold uppercase tracking-wide text-mute">
        {heading}
      </h2>

      {results === null ? (
        <p className="text-[14px] text-mute">Recherche…</p>
      ) : results.length === 0 ? (
        <p className="rounded-card border border-line bg-card px-4 py-4 text-[14px] text-ink-2">
          {query.length >= 2
            ? "Aucun spot de ce nom dans le catalogue. Tu peux l'ajouter depuis le profil."
            : "Aucun favori pour l'instant. Cherche un spot par son nom."}
        </p>
      ) : (
        <ul className="overflow-hidden rounded-card border border-line bg-card">
          {results.map((hit) => (
            <Row
              key={hit.id}
              hit={hit}
              selected={hit.id === selectedId}
              onSelect={(slug, selectedHit) => {
                onSelect(slug, selectedHit);
                onClose();
              }}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
