"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { NutritionSettings } from "@/components/nutrition/NutritionSettings";
import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { FavoriteSpots } from "@/components/surf/FavoriteSpots";
import { SpotPicker } from "@/components/surf/SpotPicker";
import { TileMap } from "@/components/surf/TileMap";
import {
  IconBoard,
  IconChevronRight,
  IconCrosshair,
  IconKey,
  IconLog,
  IconLogout,
  IconStar,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { useGeolocation } from "@/lib/useGeolocation";

/**
 * Spot favori, domicile et rayon.
 *
 * Le **spot favori** est le réglage qui compte : c'est sa prévision qui
 * s'affiche sur Jour, et c'est le seul spot interrogé toutes les trois heures,
 * app fermée.
 *
 * Le **rayon** ne décide plus de ce qui est ingéré — plus rien n'est interrogé
 * sans qu'on l'ait ouvert. Il ne sert qu'à cadrer la recherche « autour de
 * moi » de l'écran Surf.
 */
const RADIUS_STEPS = [10, 20, 30, 40, 60, 80, 100];

export default function ProfilPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const geolocation = useGeolocation();

  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: api.preferences,
  });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });

  const homeSpotId = me.data?.profile?.home_spot_id ?? null;
  const homeSpot = useQuery({
    queryKey: ["spot", homeSpotId],
    queryFn: () => api.spot(homeSpotId as number),
    enabled: homeSpotId !== null,
  });

  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftHome, setDraftHome] = useState<{ lat: number; lon: number } | null>(
    null,
  );

  const setFavoriteSpot = useMutation({
    mutationFn: (spotId: number) => api.updateProfile({ home_spot_id: spotId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      queryClient.invalidateQueries({ queryKey: ["spot-favorites"] });
    },
  });

  const save = useMutation({
    mutationFn: (data: {
      radius_km?: number;
      home_lat?: number;
      home_lon?: number;
    }) => api.updatePreferences(data),
    onSuccess: () => {
      setDraftHome(null);
      queryClient.invalidateQueries({ queryKey: ["preferences"] });
      queryClient.invalidateQueries({ queryKey: ["recommend"] });
      queryClient.invalidateQueries({ queryKey: ["spots-nearby"] });
    },
  });

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
      router.replace("/login");
    },
  });

  if (preferences.isPending) {
    return (
      <>
        <ScreenHeader title="Profil" />
        <p className="px-5 text-[14px] text-mute">Chargement…</p>
      </>
    );
  }

  const current = preferences.data;
  const home =
    draftHome ??
    (current?.home_lat !== null &&
    current?.home_lat !== undefined &&
    current?.home_lon !== null &&
    current?.home_lon !== undefined
      ? { lat: current.home_lat, lon: current.home_lon }
      : geolocation.position);

  const radius = current?.radius_km ?? 40;

  return (
    <>
      <ScreenHeader
        title="Profil"
        subtitle={me.data?.email ?? undefined}
      />

      {/* Le matos et l'historique sont passés dans Surf le 13/09 : le profil
          redevient ce qu'il doit être, des réglages. Les deux lignes restent
          ici parce qu'on y arrive par le raisonnement « c'est à moi », pas
          parce qu'elles y vivent. */}
      <section className="px-5 pb-6">
        <ul className="overflow-hidden rounded-card border border-line bg-card">
          {[
            {
              href: "/profil/jetons",
              label: "Raccourci iPhone",
              hint: "Jeton Bearer, révocable",
              Icon: IconKey,
            },
            {
              href: "/surf/matos",
              label: "Matos",
              hint: "Planches et combinaisons — dans Surf",
              Icon: IconBoard,
            },
            {
              href: "/surf/sessions",
              label: "Sessions",
              hint: "L'historique, et ce qui reste à noter — dans Surf",
              Icon: IconLog,
            },
          ].map(({ href, label, hint, Icon }) => (
            <li key={href} className="border-b border-line last:border-0">
              <Link
                href={href}
                className="flex min-h-touch items-center gap-3 px-4 py-2.5"
              >
                <Icon className="h-5 w-5 shrink-0 text-mute" />
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-semibold text-ink">
                    {label}
                  </span>
                  <span className="block truncate text-[12px] text-mute">
                    {hint}
                  </span>
                </span>
                <IconChevronRight className="h-4 w-4 shrink-0 text-mute" />
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="px-5 pb-6">
        <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Spot favori
        </h2>

        <div className="flex items-center gap-3 rounded-card border border-line bg-card px-4 py-3">
          <IconStar
            className={`h-5 w-5 shrink-0 ${
              homeSpotId !== null ? "text-accent" : "text-mute"
            }`}
            filled={homeSpotId !== null}
          />
          <p className="min-w-0 flex-1 truncate text-[16px] font-semibold text-ink">
            {homeSpot.data?.name ?? "Aucun spot choisi"}
          </p>
          <button
            type="button"
            onClick={() => setPickerOpen((open) => !open)}
            className="min-h-touch shrink-0 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2"
          >
            {pickerOpen ? "Fermer" : "Changer"}
          </button>
        </div>
        <p className="mt-2 text-[12px] text-mute">
          Sa prévision est celle de l&apos;écran Jour. Lui et les autres favoris
          sont interrogés toutes les trois heures, app fermée.
        </p>
      </section>

      {/* Les autres favoris, leur ordre, et lequel est le principal. Deux
          notions distinctes : réordonner ne change pas l'écran Jour, sans quoi
          on n'oserait plus réordonner (décidé le 13/09). */}
      <FavoriteSpots homeSpotId={homeSpotId} />

      {/* Ce que la cible calorique a besoin de savoir. Quatre réglages qu'on
          ne touche qu'une fois, et sans lesquels la cible reste une estimation
          qui se signale (lot 5). */}
      <NutritionSettings />

      {pickerOpen ? (
        <div className="-mt-2 pb-6">
          <SpotPicker
            selectedId={homeSpotId}
            onSelect={(slug) => {
              // Le sélecteur rend un slug ; le profil stocke un identifiant.
              api.spot(slug).then((spot) => setFavoriteSpot.mutate(spot.id));
            }}
            onClose={() => setPickerOpen(false)}
          />
        </div>
      ) : null}

      <section className="px-5">
        <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Domicile
        </h2>

        {home ? (
          <>
            <TileMap
              center={home}
              zoom={10}
              className="h-[38vh] min-h-[220px]"
              markers={[
                {
                  id: "home",
                  lat: home.lat,
                  lon: home.lon,
                  label: "Domicile",
                  highlight: true,
                },
              ]}
              onLongPress={(position) => setDraftHome(position)}
            />
            <p className="tabular mt-2 text-[12px] text-mute">
              {home.lat.toFixed(4)}, {home.lon.toFixed(4)} — appui long sur la
              carte pour déplacer.
            </p>
          </>
        ) : (
          <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
            Aucun domicile. Utilise ta position courante ci-dessous.
          </p>
        )}

        <div className="mt-3 flex gap-3">
          <button
            type="button"
            disabled={!geolocation.position}
            onClick={() =>
              geolocation.position && setDraftHome(geolocation.position)
            }
            className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink disabled:opacity-50"
          >
            <IconCrosshair className="h-5 w-5" />
            Ma position
          </button>
          <button
            type="button"
            disabled={!draftHome || save.isPending}
            onClick={() =>
              draftHome &&
              save.mutate({ home_lat: draftHome.lat, home_lon: draftHome.lon })
            }
            className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-50"
          >
            {save.isPending ? "Enregistrement…" : "Enregistrer"}
          </button>
        </div>
      </section>

      <section className="px-5 pt-6">
        <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Rayon de recherche
        </h2>
        <div className="flex flex-wrap gap-2">
          {RADIUS_STEPS.map((step) => (
            <button
              key={step}
              type="button"
              onClick={() => save.mutate({ radius_km: step })}
              aria-pressed={Math.round(radius) === step}
              className={`tabular min-h-touch min-w-[64px] rounded-pill border px-4 text-[15px] font-semibold ${
                Math.round(radius) === step
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              {step} km
            </button>
          ))}
        </div>
        <p className="mt-2 text-[12px] text-mute">
          Cadre la recherche « autour de moi » sur l&apos;écran Surf. Aucun de
          ces spots n&apos;est interrogé tant que tu ne l&apos;ouvres pas.
        </p>
      </section>

      {(current?.hidden_spot_ids.length ?? 0) > 0 ? (
        <section className="px-5 pt-6">
          <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Spots masqués
          </h2>
          <p className="rounded-card border border-line bg-card px-4 py-3 text-[13px] text-ink-2">
            {current?.hidden_spot_ids.length} spot(s) masqué(s). Ouvre la fiche
            d&apos;un spot pour le réafficher.
          </p>
        </section>
      ) : null}

      <section className="px-5 pb-6 pt-8">
        <button
          type="button"
          onClick={() => logout.mutate()}
          className="flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
        >
          <IconLogout className="h-5 w-5" />
          Se déconnecter
        </button>
      </section>
    </>
  );
}
