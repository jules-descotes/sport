"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { SpotRulesForm } from "@/components/surf/SpotRulesForm";
import { SwellChart } from "@/components/surf/SwellChart";
import { Webcam } from "@/components/surf/Webcam";
import { IconBack, IconCamera, IconEyeOff, IconStar } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import { compass, num, scoreClass } from "@/lib/format";

/**
 * Fiche spot : webcam, courbe de houle sur cinq jours, niveau de la mer,
 * favori secondaire et masquage.
 *
 * Ce n'est pas une destination — la barre basse en compte trois, et elle n'en
 * comptera pas quatre. C'est le détail d'un spot, ouvert depuis l'écran Surf
 * pour ce que la grille ne montre pas : la webcam et la forme de la houle sur
 * cinq jours.
 *
 * Le favori **du profil** se définit sur Surf : c'est lui qui porte l'écran
 * Jour. Le bouton ci-dessous ajoute un favori *secondaire* — vingt au maximum,
 * ingérés en planifié eux aussi.
 */
export default function SpotPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const queryClient = useQueryClient();

  const forecast = useQuery({
    queryKey: ["spot-forecast", slug],
    queryFn: () => api.spotForecast(slug),
    refetchInterval: (query) => (query.state.data?.refreshing ? 6_000 : false),
  });

  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: api.preferences,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["preferences"] });
    queryClient.invalidateQueries({ queryKey: ["recommend"] });
  };

  const favorite = useMutation({
    mutationFn: (next: boolean) => api.setFavorite(slug, next),
    onSuccess: invalidate,
  });

  const hide = useMutation({
    mutationFn: (next: boolean) => api.setHidden(slug, next),
    onSuccess: invalidate,
  });

  if (forecast.isPending) {
    return <p className="px-5 py-10 text-[14px] text-mute">Chargement…</p>;
  }

  if (forecast.error || !forecast.data) {
    const missing =
      forecast.error instanceof ApiError && forecast.error.status === 404;
    return (
      <main className="px-5 py-10 text-center">
        <p className="text-[16px] text-ink">
          {missing ? "Ce spot n'existe pas." : "Prévisions indisponibles."}
        </p>
        <Link href="/surf" className="mt-4 inline-block text-[14px] text-accent">
          Retour à Surf
        </Link>
      </main>
    );
  }

  const { spot, points } = forecast.data;
  const isFavorite = preferences.data?.favorite_spot_ids.includes(spot.id) ?? false;
  const isHidden = preferences.data?.hidden_spot_ids.includes(spot.id) ?? false;
  const next = points[0];

  return (
    <main className="pb-6">
      <header className="flex items-start gap-2 px-4 pb-3 pt-4">
        <Link
          href="/surf"
          aria-label="Retour"
          className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-6 w-6" />
        </Link>
        <div className="min-w-0 flex-1 pt-2">
          <h1 className="truncate font-display text-[28px] leading-none font-semibold uppercase text-ink">
            {spot.name}
          </h1>
          <p className="mt-1 text-[12px] text-mute">
            {spot.onshore_dir_deg !== null
              ? `Regarde vers le ${compass(spot.onshore_dir_deg)}`
              : "Orientation de côte inconnue"}
            {spot.source === "user" ? " · ajouté à la main" : ""}
          </p>
        </div>
        {next?.score_level ? (
          <span
            className={`tabular flex h-12 w-12 shrink-0 items-center justify-center rounded-cell font-display text-[20px] font-bold ${scoreClass(
              next.score_level,
            )}`}
          >
            {num(next.score, 1)}
          </span>
        ) : null}
      </header>

      {/* Les critères de Jules pour ce spot (décidé le 13/09). Juste sous le
          nom : c'est ce qui décide de la note et des annonces de Jour, donc
          ça vaut mieux que la webcam. */}
      <SpotRulesForm slug={slug} />

      {/* Webcam : iframe ou lien sortant, jamais de ré-hébergement du flux
          (droits et bande passante, cf. PROJET.md §10). Le choix entre les
          deux est dans `components/surf/Webcam.tsx`. */}
      <section className="px-5">
        <Webcam url={spot.webcam_url} name={spot.name} />
        <WebcamForm slug={slug} current={spot.webcam_url} />
      </section>

      <section className="px-5 pt-5">
        <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Houle sur 5 jours
        </h2>
        <SwellChart points={points} />
      </section>

      {next ? (
        <section className="px-5 pt-5">
          <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Maintenant
          </h2>
          <dl className="tabular grid grid-cols-2 gap-2">
            {[
              ["Houle", `${num(next.wave_height_m)} m`],
              // Période moyenne, la seule que MFWAM serve — et la seule sur
              // laquelle la note est calculée. Afficher le pic ici donnerait
              // un chiffre qui ne correspond à rien de ce qui est noté.
              ["Période", `${num(next.wave_period_s, 0)} s`],
              ["Direction", compass(next.wave_direction_deg)],
              [
                "Vent",
                `${compass(next.wind_direction_deg)} ${num(next.wind_speed_kt, 0)} kt`,
              ],
              ["Rafales", `${num(next.wind_gust_kt, 0)} kt`],
              ["Eau", `${num(next.water_temperature_c, 0)} °C`],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-cell border border-line bg-card px-3 py-2"
              >
                <dt className="text-[11px] uppercase tracking-wide text-mute">
                  {label}
                </dt>
                <dd className="text-[18px] font-semibold text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <section className="flex gap-3 px-5 pt-6">
        <button
          type="button"
          onClick={() => favorite.mutate(!isFavorite)}
          disabled={favorite.isPending}
          aria-pressed={isFavorite}
          className={`flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button border px-4 text-[15px] font-semibold disabled:opacity-60 ${
            isFavorite
              ? "border-accent bg-accent text-on-accent"
              : "border-line bg-card text-ink"
          }`}
        >
          <IconStar className="h-5 w-5" filled={isFavorite} />
          {isFavorite ? "Spot maison" : "Ajouter aux spots maison"}
        </button>
        <button
          type="button"
          onClick={() => hide.mutate(!isHidden)}
          disabled={hide.isPending}
          aria-pressed={isHidden}
          className="flex min-h-touch w-touch items-center justify-center rounded-button border border-line bg-card text-ink-2 disabled:opacity-60"
          aria-label={isHidden ? "Ne plus masquer" : "Masquer ce spot"}
        >
          <IconEyeOff className="h-5 w-5" />
        </button>
      </section>

      {favorite.error instanceof ApiError ? (
        <p role="alert" className="px-5 pt-3 text-[13px] text-accent">
          {favorite.error.message}
        </p>
      ) : null}

      {isFavorite ? (
        <p className="px-5 pt-3 text-[12px] text-mute">
          Les spots maison sont interrogés toutes les trois heures, même app
          fermée.
        </p>
      ) : null}
    </main>
  );
}

/**
 * Saisie de l'URL de webcam d'un spot.
 *
 * Repliée : c'est un geste qu'on fait une fois par spot maison, pas tous les
 * matins. Le back refuse le `http:` et réécrit en `https:` quand le site le
 * sert — le message d'erreur qu'il rend est affiché tel quel, parce qu'il dit
 * exactement quoi faire.
 */
function WebcamForm({
  slug,
  current,
}: {
  slug: string;
  current: string | null;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState(current ?? "");

  const save = useMutation({
    mutationFn: (value: string) =>
      api.updateSpot(slug, { webcam_url: value.trim() || null }),
    onSuccess: () => {
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["spot-forecast", slug] });
    },
  });

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[14px] font-semibold text-ink-2"
      >
        <IconCamera className="h-5 w-5" />
        {current ? "Changer la webcam" : "Ajouter une webcam"}
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-card border border-line bg-card p-4">
      <label
        htmlFor="webcam-url"
        className="block pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute"
      >
        Adresse de la webcam
      </label>
      <input
        id="webcam-url"
        type="url"
        inputMode="url"
        autoComplete="off"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="https://…"
        className="min-h-touch w-full rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
      />
      <p className="mt-2 text-[12px] leading-snug text-mute">
        En https uniquement : une webcam en clair est bloquée comme contenu
        mixte, et ne montrerait qu&apos;un cadre blanc.
      </p>

      {save.error instanceof ApiError ? (
        <p role="alert" className="mt-2 text-[13px] leading-snug text-accent">
          {save.error.message}
        </p>
      ) : null}

      <div className="mt-3 flex gap-3">
        <button
          type="button"
          onClick={() => {
            setUrl(current ?? "");
            setOpen(false);
          }}
          className="min-h-touch flex-1 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
        >
          Annuler
        </button>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate(url)}
          className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-50"
        >
          {save.isPending ? "Vérification…" : "Enregistrer"}
        </button>
      </div>
    </div>
  );
}
