"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { TileMap } from "@/components/surf/TileMap";
import { IconCrosshair, IconLogout } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { useGeolocation } from "@/lib/useGeolocation";

/**
 * Domicile et rayon d'affichage.
 *
 * Ces deux réglages décident de ce qui est ingéré : tout spot dans le rayon
 * devient « potentiel » et sera interrogé à l'ouverture de l'app. Élargir le
 * rayon coûte des appels — d'où le curseur plutôt qu'un champ libre, et le
 * plafond à 100 km.
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

  const [draftHome, setDraftHome] = useState<{ lat: number; lon: number } | null>(
    null,
  );

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
          Rayon d&apos;affichage
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
          Les spots dans ce rayon sont interrogés à l&apos;ouverture de
          l&apos;app. Les favoris, eux, le sont toutes les trois heures.
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
