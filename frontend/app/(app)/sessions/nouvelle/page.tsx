"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import {
  SessionForm,
  type SessionFormValues,
} from "@/components/session/SessionForm";
import { IconBack } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import { floorToQuarter, minutesBetween } from "@/lib/format";

/**
 * **Ajouter une session depuis le navigateur** (décidé le 13/09).
 *
 * Le raccourci iPhone reste le chemin normal — quinze secondes, sortie de
 * l'eau, le serveur devine le reste. Mais il ne couvre pas tout : un téléphone
 * resté dans la voiture, une session d'il y a trois semaines qu'on retrouve
 * dans sa tête, un trip dont on saisit les six sessions au retour. Sans cet
 * écran, ces sessions-là n'existent pas, et ce sont des lignes
 * d'apprentissage perdues.
 *
 * Le serveur fait **exactement** le même travail que pour une session du
 * raccourci : backfill de l'archive Open-Meteo sur la fenêtre T−2 h → T0, et
 * volet `forecast` borné aux runs **émis avant le début**. Y compris pour une
 * date passée : une passe d'ingestion postérieure à la session est un constat
 * déguisé, et la retenir serait du décalage train/serve (`PROJET.md` §7.1).
 *
 * Les deux notes sont exigées ici, contrairement au chemin rapide : on saisit
 * au sec, à tête reposée. Une session créée sans note serait une ligne sans
 * étiquette, et il faudrait y revenir.
 */

/** Durée par défaut — la session type, corrigée aux molettes. */
const DEFAULT_DURATION_MIN = 90;

function NewSessionScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const requestedSpotId = Number(searchParams.get("spot")) || null;

  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const homeSpotId = me.data?.profile?.home_spot_id ?? null;

  const favorites = useQuery({
    queryKey: ["spot-favorites"],
    queryFn: api.favoriteSpots,
  });

  // Une session commence rarement à l'heure pile où l'on ouvre l'écran : on
  // propose la dernière heure ronde, reculée d'une heure et demie. C'est le
  // même défaut que le chemin rapide, pour que les deux racontent pareil.
  const [form, setForm] = useState<SessionFormValues>(() => {
    const end = floorToQuarter(new Date());
    return {
      spotId: requestedSpotId,
      start: new Date(end.getTime() - DEFAULT_DURATION_MIN * 60_000),
      end,
      conditions: null,
      personal: null,
      // `undefined` : la dernière planche utilisée sera proposée.
      gearId: undefined,
      waves: 0,
      notes: "",
      segments: [],
    };
  });

  // Le favori du profil est présélectionné : c'est le spot de neuf sessions
  // sur dix, et un défaut juste vaut mieux qu'un champ vide.
  const spotId = form.spotId ?? homeSpotId;

  const suggestions = useMemo(() => favorites.data ?? [], [favorites.data]);

  // Même règle que sur l'écran de notation : la dernière planche utilisée est
  // proposée d'office, dérivée et non posée dans un état.
  const gear = useQuery({ queryKey: ["gear", "active"], queryFn: () => api.gear(false) });
  const defaultGearId = useMemo(() => {
    const lastUsed = (gear.data ?? [])
      .filter((item) => item.gear_type === "board" && item.last_used_at !== null)
      .sort(
        (a, b) =>
          new Date(b.last_used_at as string).getTime() -
          new Date(a.last_used_at as string).getTime(),
      )[0];
    return lastUsed?.id ?? null;
  }, [gear.data]);
  const gearId = form.gearId === undefined ? defaultGearId : form.gearId;
  const spotName =
    suggestions.find((hit) => hit.id === spotId)?.name ?? null;

  const create = useMutation({
    mutationFn: () =>
      api.createSession({
        spot_id: spotId as number,
        started_at: form.start.toISOString(),
        duration_min: Math.max(15, minutesBetween(form.start, form.end)),
        rating_conditions: form.conditions as number,
        rating_personal: form.personal as number,
        ...(gearId != null ? { gear_id: gearId } : {}),
        wave_count: form.waves,
        ...(form.notes.trim() ? { notes: form.notes.trim() } : {}),
        ...(form.segments.length ? { segments: form.segments } : {}),
      }),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session-journal"] });
      queryClient.invalidateQueries({ queryKey: ["gear"] });
      router.replace(`/sessions/${session.id}`);
    },
  });

  const complete =
    spotId !== null && form.conditions !== null && form.personal !== null;

  return (
    <main className="pb-10">
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Retour"
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Ajouter une session
        </p>
      </header>

      <SessionForm
        values={{ ...form, spotId, gearId }}
        onChange={setForm}
        spotName={spotName}
        suggestions={suggestions}
        suggestionsPending={favorites.isPending}
        showDate
        hint="appuie pour choisir le spot"
      />

      <div className="px-5 pt-6">
        <button
          type="button"
          disabled={!complete || create.isPending}
          onClick={() => create.mutate()}
          className="flex min-h-[56px] w-full items-center justify-center rounded-button bg-accent px-5 text-[17px] font-semibold text-on-accent disabled:opacity-40"
        >
          {create.isPending ? "Enregistrement…" : "Enregistrer la session"}
        </button>

        {!complete ? (
          <p className="mt-2.5 text-center text-[13px] text-mute">
            {spotId === null
              ? "Choisis un spot."
              : "Les deux notes, pas une seule."}
          </p>
        ) : (
          <p className="mt-2.5 text-center text-[13px] leading-snug text-mute">
            Les conditions de cette date seront remontées de l&apos;archive à
            l&apos;enregistrement, même pour un spot jamais ouvert.
          </p>
        )}

        {create.error ? (
          <p className="mt-2.5 text-center text-[13px] text-ink-2">
            {create.error instanceof ApiError && create.error.status === 0
              ? "Pas de réseau. Une session se crée en ligne — le raccourci iPhone, lui, marche hors ligne."
              : "Enregistrement impossible. Réessaie."}
          </p>
        ) : null}
      </div>
    </main>
  );
}

export default function NewSessionPage() {
  // `useSearchParams` impose une frontière de Suspense : sans elle, le rendu
  // statique de Next échoue au build.
  return (
    <Suspense
      fallback={<p className="px-5 py-10 text-[14px] text-mute">Chargement…</p>}
    >
      <NewSessionScreen />
    </Suspense>
  );
}
