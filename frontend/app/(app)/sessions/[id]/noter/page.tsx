"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  PhotoField,
  SessionForm,
  type SessionFormValues,
} from "@/components/session/SessionForm";
import { IconBack, IconCloudOff } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import type { SessionUpdate } from "@/lib/api";
import { floorToQuarter, minutesBetween, sessionEnd } from "@/lib/format";
import { useOfflineQueue } from "@/lib/useOfflineQueue";

/**
 * **Noter la session**, et la corriger — le second temps de la saisie.
 *
 * Le chemin rapide a fait le plus dur : la session existe, le spot est deviné,
 * les conditions sont figées. Ce qui reste tient en un écran, et tout s'y fait
 * au doigt (cf. `components/session/SessionForm.tsx` pour les règles).
 *
 * Depuis le 13/09, **tous** les champs saisis sont modifiables ici, y compris
 * la date et le spot cherché dans tout le catalogue — et pas seulement à la
 * première notation. Changer le spot ou l'heure refait le figeage des
 * conditions côté serveur, et l'ancien snapshot est **empilé, jamais écrasé** :
 * c'est la seule donnée du projet qu'on ne peut pas reconstituer après coup.
 *
 * Et tout marche **sans réseau** : si l'envoi échoue faute de réseau, la
 * notation part dans la file IndexedDB et l'écran le dit, sobrement.
 */

/** Les cinq spots les plus proches, proposés quand le spot deviné est faux. */
const SPOT_CHOICES = 5;

export default function NoterPage() {
  const params = useParams<{ id: string }>();
  const sessionId = Number(params.id);
  const router = useRouter();
  const queryClient = useQueryClient();
  const offline = useOfflineQueue();

  const { data, isPending, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.session(sessionId),
    enabled: Number.isFinite(sessionId),
  });

  const gear = useQuery({
    queryKey: ["gear", "active"],
    queryFn: () => api.gear(false),
  });

  const [form, setForm] = useState<SessionFormValues | null>(null);
  const [spotTouched, setSpotTouched] = useState(false);
  const [queued, setQueued] = useState(false);

  // Une seule reprise depuis le serveur : re-remplir à chaque revalidation
  // effacerait la saisie en cours sous les doigts.
  const loaded = useRef(false);
  useEffect(() => {
    if (!data || loaded.current) return;
    loaded.current = true;

    setForm({
      spotId: data.spot_id,
      start: floorToQuarter(new Date(data.started_at)),
      end: floorToQuarter(sessionEnd(data.started_at, data.duration_min ?? 90)),
      conditions: data.rating_conditions,
      personal: data.rating_personal,
      // `undefined` : la planche n'a pas été touchée, le défaut s'applique.
      gearId: undefined,
      waves: data.wave_count ?? 0,
      notes: data.notes ?? "",
      segments: data.segments,
    });
  }, [data]);

  /**
   * La planche proposée : celle de la session si elle en a déjà une, sinon la
   * dernière utilisée — juste neuf fois sur dix, et corrigé d'un tap la
   * dixième.
   *
   * **Dérivée, pas posée dans un effet.** Un défaut n'est pas un état : le
   * copier au premier rendu obligerait à le recopier quand la liste du matos
   * arrive, ce qui écraserait un choix fait entre-temps.
   */
  const defaultGearId = useMemo(() => {
    if (!data || !gear.data) return null;
    if (data.gear_id !== null) return data.gear_id;

    const lastUsed = gear.data
      .filter((item) => item.gear_type === "board" && item.last_used_at !== null)
      .sort(
        (a, b) =>
          new Date(b.last_used_at as string).getTime() -
          new Date(a.last_used_at as string).getTime(),
      )[0];
    return lastUsed?.id ?? null;
  }, [data, gear.data]);

  // Les cinq spots les plus proches du point d'entrée à l'eau — demandés
  // seulement quand on touche au sélecteur, jamais à l'ouverture de l'écran.
  const nearby = useQuery({
    queryKey: ["session-nearby", data?.lat, data?.lon, data?.spot?.id],
    queryFn: () =>
      api.spotsNearby({
        lat: data?.lat ?? (data?.spot?.lat as number),
        lon: data?.lon ?? (data?.spot?.lon as number),
        radius_km: 25,
      }),
    enabled: spotTouched && data !== undefined && data.spot !== null,
  });

  const suggestions = useMemo(
    () =>
      (nearby.data ?? []).slice(0, SPOT_CHOICES).map((spot) => ({
        ...spot,
        is_home: spot.is_home,
      })),
    [nearby.data],
  );

  const save = useMutation({
    mutationFn: async (payload: SessionUpdate) => {
      try {
        return await api.updateSession(sessionId, payload);
      } catch (err) {
        // Parking de plage, pas de barre : la notation ne se perd pas, elle
        // attend. C'est la règle du hors-ligne réel (`PROJET.md` §1, règle 6).
        if (err instanceof ApiError && err.status === 0) {
          const stored = await offline.queue(sessionId, payload);
          if (stored) return null;
        }
        throw err;
      }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["session-journal"] });
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["gear"] });
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      if (result === null) {
        setQueued(true);
        return;
      }
      router.push(`/sessions/${sessionId}`);
    },
  });

  const photo = useMutation({
    mutationFn: (file: File) => api.uploadSessionPhoto(sessionId, file),
    onSuccess: (updated) => {
      queryClient.setQueryData(["session", sessionId], updated);
    },
  });

  if (isPending || !form) {
    return (
      <main className="px-5 py-10">
        <p className="text-[14px] text-mute">Chargement de la session…</p>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="px-5 py-10 text-center">
        <p className="text-[16px] text-ink">Session introuvable.</p>
        <button
          type="button"
          onClick={() => router.push("/")}
          className="mt-4 min-h-touch rounded-button border border-line bg-card px-5 text-[15px] font-semibold text-ink-2"
        >
          Retour au jour
        </button>
      </main>
    );
  }

  if (queued) return <QueuedConfirmation sessionId={sessionId} />;

  // Les deux notes, jamais une seule : le bouton reste inerte tant qu'il en
  // manque une (cf. CLAUDE.md, règle 6).
  const complete = form.conditions !== null && form.personal !== null;
  const gearId = form.gearId === undefined ? defaultGearId : form.gearId;
  const alreadyRated = data.status === "rated";
  const movedSpot = form.spotId !== data.spot_id;
  const movedHour =
    new Date(data.started_at).getUTCHours() !== form.start.getUTCHours() ||
    new Date(data.started_at).toDateString() !== form.start.toDateString();

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
          {alreadyRated ? "Modifier la session" : "Noter la session"}
        </p>
      </header>

      <div onPointerDownCapture={() => setSpotTouched(true)}>
        <SessionForm
          values={{ ...form, gearId }}
          onChange={setForm}
          spotName={data.spot?.name ?? null}
          suggestions={suggestions}
          suggestionsPending={nearby.isPending && spotTouched}
          // La date est modifiable ici aussi depuis le 13/09 : une session
          // ancienne se corrige de bout en bout, pas seulement son heure.
          showDate={alreadyRated || data.start_estimated}
          hint={
            data.start_estimated
              ? "début estimé par le serveur — corrige si besoin"
              : undefined
          }
          photoSlot={
            <PhotoField
              hasPhoto={data.photo_url !== null}
              pending={photo.isPending}
              onPick={(file) => photo.mutate(file)}
              url={data.photo_url}
              error={
                photo.error
                  ? photo.error instanceof ApiError && photo.error.status === 0
                    ? "Photo impossible sans réseau — la note, elle, part quand même."
                    : "Photo non enregistrée."
                  : null
              }
            />
          }
        />
      </div>

      {/* Changer le spot ou l'heure refait le figeage des conditions. On le
          dit avant d'enregistrer, pas après : c'est la ligne d'apprentissage
          de cette session qui change. L'ancienne version est conservée. */}
      {(movedSpot || movedHour) && data.conditions_snapshot ? (
        <p className="mx-5 mt-4 rounded-card border border-dashed border-line bg-soft px-4 py-3 text-[13px] leading-snug text-ink-2">
          {movedSpot && movedHour
            ? "Spot et heure modifiés"
            : movedSpot
              ? "Spot modifié"
              : "Heure modifiée"}{" "}
          : les conditions figées vont être refaites. L&apos;ancienne version
          est conservée dans l&apos;historique de la session.
        </p>
      ) : null}

      {offline.pending > 0 ? (
        <p className="flex items-center gap-2 px-5 pt-4 text-[13px] text-mute">
          <IconCloudOff className="h-4 w-4 shrink-0" />
          {offline.pending} notation(s) en attente d&apos;envoi
        </p>
      ) : null}

      <div className="px-5 pt-6">
        <button
          type="button"
          disabled={!complete || save.isPending}
          onClick={() =>
            save.mutate({
              spot_id: form.spotId ?? data.spot_id,
              started_at: form.start.toISOString(),
              duration_min: Math.max(15, minutesBetween(form.start, form.end)),
              rating_conditions: form.conditions as number,
              rating_personal: form.personal as number,
              ...(gearId !== null ? { gear_id: gearId } : {}),
              wave_count: form.waves,
              notes: form.notes.trim() || null,
              // Toujours envoyés : l'écran porte l'état entier de la frise, et
              // une liste vide est la façon d'effacer un détail horaire posé
              // par erreur.
              segments: form.segments,
            })
          }
          className="flex min-h-[56px] w-full items-center justify-center rounded-button bg-accent px-5 text-[17px] font-semibold text-on-accent disabled:opacity-40"
        >
          {save.isPending ? "Enregistrement…" : "Enregistrer"}
        </button>

        {!complete ? (
          <p className="mt-2.5 text-center text-[13px] text-mute">
            Les deux notes, pas une seule.
          </p>
        ) : null}
        {save.error ? (
          <p className="mt-2.5 text-center text-[13px] text-ink-2">
            Enregistrement impossible. Réessaie.
          </p>
        ) : null}
      </div>
    </main>
  );
}

/**
 * Ce qu'on voit quand la notation est partie en file plutôt qu'au serveur.
 *
 * Pas une erreur, et surtout pas une alerte : c'est le fonctionnement prévu
 * sur le parking. On dit ce qui s'est passé, et on laisse partir.
 */
function QueuedConfirmation({ sessionId }: { sessionId: number }) {
  const router = useRouter();
  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center gap-4 px-8 text-center">
      <IconCloudOff className="h-10 w-10 text-mute" />
      <p className="font-display text-[30px] font-bold leading-none uppercase text-ink">
        Gardée au chaud
      </p>
      <p className="max-w-[300px] text-[15px] leading-snug text-ink-2">
        Pas de réseau. La notation part toute seule dès que la connexion
        revient — tu peux fermer l&apos;app.
      </p>
      <button
        type="button"
        onClick={() => router.push(`/sessions/${sessionId}`)}
        className="mt-2 min-h-touch rounded-button border border-line bg-card px-5 text-[15px] font-semibold text-ink-2"
      >
        Voir la session
      </button>
    </main>
  );
}
