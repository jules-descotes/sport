"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import {
  IconChevronDown,
  IconSliders,
  IconStar,
  IconTrash,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import type { SpotHit } from "@/lib/types";

/**
 * **Les favoris**, avec leur ordre et leur principal (décidé le 13/09).
 *
 * Deux notions distinctes, et les confondre serait une erreur :
 *
 * - **Le favori principal** (`profiles.home_spot_id`) est celui dont la
 *   prévision occupe l'écran Jour. Il n'y en a qu'un.
 * - **L'ordre** des favoris décide de ce que propose le sélecteur de l'écran
 *   Surf, et départage deux annonces à la même heure. Réordonner ne doit pas
 *   changer l'écran Jour, sans quoi on n'oserait plus réordonner.
 *
 * Le déplacement se fait par **flèches et non par glisser-déposer** : un
 * glisser-déposer se rate une fois sur trois avec un doigt mouillé, et il n'y a
 * pas de retour en arrière. Deux boutons de 44 px marchent à tous les coups.
 */
export function FavoriteSpots({ homeSpotId }: { homeSpotId: number | null }) {
  const queryClient = useQueryClient();

  const favorites = useQuery({
    queryKey: ["spot-favorites"],
    queryFn: api.favoriteSpots,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["spot-favorites"] });
    queryClient.invalidateQueries({ queryKey: ["recommend"] });
  };

  const reorder = useMutation({
    mutationFn: (spotIds: number[]) => api.reorderFavorites(spotIds),
    onSuccess: (spots) => {
      queryClient.setQueryData(["spot-favorites"], spots);
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
    },
  });

  const setHome = useMutation({
    mutationFn: (spotId: number) => api.updateProfile({ home_spot_id: spotId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      invalidate();
    },
  });

  const remove = useMutation({
    mutationFn: (ref: string) => api.setFavorite(ref, false),
    onSuccess: invalidate,
  });

  const spots: SpotHit[] = favorites.data ?? [];

  const move = (index: number, delta: number) => {
    const next = [...spots];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    reorder.mutate(next.map((spot) => spot.id));
  };

  if (favorites.isPending) {
    return (
      <section className="px-5 pb-6">
        <p className="text-[14px] text-mute">Chargement des favoris…</p>
      </section>
    );
  }

  return (
    <section className="px-5 pb-6" aria-label="Spots favoris">
      <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Favoris
      </h2>

      {spots.length === 0 ? (
        <p className="rounded-card border border-line bg-card px-4 py-3 text-[14px] leading-snug text-ink-2">
          Aucun favori. Ouvre un spot depuis Surf et touche « Définir comme
          favori » : il sera alors interrogé toutes les trois heures, app
          fermée.
        </p>
      ) : (
        <ul className="overflow-hidden rounded-card border border-line bg-card">
          {spots.map((spot, index) => {
            const principal = spot.id === homeSpotId;
            return (
              <li
                key={spot.id}
                className="flex items-center gap-2 border-b border-line px-3 py-2 last:border-0"
              >
                <span className="flex shrink-0 flex-col">
                  <button
                    type="button"
                    onClick={() => move(index, -1)}
                    disabled={index === 0 || reorder.isPending}
                    aria-label={`Monter ${spot.name}`}
                    className="flex h-[22px] w-9 items-center justify-center text-mute disabled:opacity-30"
                  >
                    <IconChevronDown className="h-4 w-4 rotate-180" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(index, 1)}
                    disabled={index === spots.length - 1 || reorder.isPending}
                    aria-label={`Descendre ${spot.name}`}
                    className="flex h-[22px] w-9 items-center justify-center text-mute disabled:opacity-30"
                  >
                    <IconChevronDown className="h-4 w-4" />
                  </button>
                </span>

                <Link
                  href={`/surf/spots/${spot.slug}`}
                  className="min-w-0 flex-1 py-1"
                >
                  <span className="block truncate text-[15px] font-semibold text-ink">
                    {spot.name}
                  </span>
                  <span className="flex items-center gap-1 text-[12px] text-mute">
                    <IconSliders className="h-3.5 w-3.5" />
                    {principal ? "Affiché sur Jour" : "Annoncé s'il correspond"}
                  </span>
                </Link>

                <button
                  type="button"
                  onClick={() => setHome.mutate(spot.id)}
                  disabled={principal || setHome.isPending}
                  aria-label={`Faire de ${spot.name} le favori principal`}
                  className={`flex h-touch w-touch shrink-0 items-center justify-center rounded-button ${
                    principal ? "text-accent" : "text-mute"
                  }`}
                >
                  <IconStar className="h-5 w-5" filled={principal} />
                </button>

                <button
                  type="button"
                  onClick={() => remove.mutate(spot.slug)}
                  disabled={remove.isPending}
                  aria-label={`Retirer ${spot.name} des favoris`}
                  className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-mute disabled:opacity-40"
                >
                  <IconTrash className="h-5 w-5" />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-2 text-[12px] leading-snug text-mute">
        L&apos;étoile désigne le favori principal — sa prévision est celle de
        Jour. Les autres sont annoncés quand un créneau correspond aux critères
        que tu leur as posés, sur leur fiche.
      </p>
    </section>
  );
}
