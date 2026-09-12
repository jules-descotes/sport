"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { RatingScale } from "@/components/session/RatingScale";
import { TimeWheel } from "@/components/session/TimeWheel";
import { WaveStepper } from "@/components/session/WaveStepper";
import {
  IconBack,
  IconBoard,
  IconCamera,
  IconChevronDown,
  IconCloudOff,
  IconPin,
} from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import type { SessionUpdate } from "@/lib/api";
import {
  boardLength,
  distanceLabel,
  durationLabel,
  floorToQuarter,
  minutesBetween,
  sessionEnd,
  shortDate,
} from "@/lib/format";
import type { Gear, SpotNearby } from "@/lib/types";
import { useOfflineQueue } from "@/lib/useOfflineQueue";

/**
 * **Noter la session** — le second temps de la saisie, plein cadre.
 *
 * Le chemin rapide a fait le plus dur : la session existe, le spot est deviné,
 * les conditions sont figées. Ce qui reste tient en un écran, et tout s'y fait
 * au doigt — cinq boutons, deux molettes, un compteur, des pastilles.
 *
 * **Aucune zone de texte n'est visible sans une action explicite.** La note
 * libre et la photo sont repliées en bas. C'est la règle « zéro saisie clavier
 * pendant l'effort » (`PROJET.md` §1, règle 5) prise au sérieux : un champ de
 * texte visible attire le doigt, ouvre le clavier, mange la moitié de l'écran,
 * et transforme une notation de quinze secondes en formulaire.
 *
 * Et tout marche **sans réseau** : si l'envoi échoue faute de réseau, la
 * notation part dans la file IndexedDB et l'écran le dit, sobrement, sans
 * bloquer quoi que ce soit.
 */

/** Les cinq spots les plus proches, proposés quand le spot deviné est faux. */
const SPOT_CHOICES = 5;

function Section({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-line px-5 py-5">
      {title ? (
        <h2 className="pb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {title}
        </h2>
      ) : null}
      {children}
    </section>
  );
}

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

  // ── État de saisie ────────────────────────────────────────────────────
  //
  // Un formulaire local plutôt qu'un envoi par champ : on écrit une seule
  // fois, au bouton, et l'écran reste utilisable sans réseau du premier tap
  // au dernier.
  const [spotId, setSpotId] = useState<number | null>(null);
  const [start, setStart] = useState<Date | null>(null);
  const [end, setEnd] = useState<Date | null>(null);
  const [conditions, setConditions] = useState<number | null>(null);
  const [personal, setPersonal] = useState<number | null>(null);
  const [gearChoice, setGearChoice] = useState<number | null | undefined>(
    undefined,
  );
  const [waves, setWaves] = useState(0);
  const [notes, setNotes] = useState("");
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [spotPickerOpen, setSpotPickerOpen] = useState(false);
  const [queued, setQueued] = useState(false);
  const photoInput = useRef<HTMLInputElement>(null);

  // Une seule reprise depuis le serveur : re-remplir à chaque revalidation
  // effacerait la saisie en cours sous les doigts.
  const loaded = useRef(false);
  useEffect(() => {
    if (!data || loaded.current) return;
    loaded.current = true;

    const startedAt = new Date(data.started_at);
    setSpotId(data.spot_id);
    setStart(floorToQuarter(startedAt));
    setEnd(floorToQuarter(sessionEnd(data.started_at, data.duration_min ?? 90)));
    setConditions(data.rating_conditions);
    setPersonal(data.rating_personal);
    setWaves(data.wave_count ?? 0);
    setNotes(data.notes ?? "");
  }, [data]);

  /**
   * La planche proposée : celle de la session si elle en a déjà une, sinon la
   * dernière utilisée — juste neuf fois sur dix, et corrigé d'un tap la
   * dixième.
   *
   * **Dérivée, pas posée dans un effet.** Un défaut n'est pas un état : le
   * copier dans `useState` au premier rendu obligerait à le recopier quand la
   * liste du matos arrive, ce qui écraserait un choix fait entre-temps.
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

  // Les cinq spots les plus proches du point d'entrée à l'eau — proposés
  // seulement quand on ouvre le sélecteur, jamais à l'ouverture de l'écran.
  const nearby = useQuery({
    queryKey: ["session-nearby", data?.lat, data?.lon],
    queryFn: () =>
      api.spotsNearby({
        lat: data?.lat ?? (data?.spot?.lat as number),
        lon: data?.lon ?? (data?.spot?.lon as number),
        radius_km: 25,
      }),
    enabled:
      spotPickerOpen &&
      (data?.lat !== null || data?.spot !== null) &&
      data !== undefined,
  });

  const durationMin = useMemo(
    () => (start && end ? minutesBetween(start, end) : 0),
    [start, end],
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

  if (isPending || !start || !end) {
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

  const spot = data.spot;
  const chosenSpot =
    spotId === data.spot_id
      ? spot
      : ((nearby.data?.find((item) => item.id === spotId) as
          | SpotNearby
          | undefined) ?? spot);
  const boards: Gear[] = (gear.data ?? []).filter(
    (item) => item.gear_type === "board",
  );
  const gearId = gearChoice === undefined ? defaultGearId : gearChoice;
  // Les deux notes, jamais une seule : le bouton reste inerte tant qu'il en
  // manque une (cf. CLAUDE.md, règle 6).
  const complete = conditions !== null && personal !== null;

  if (queued) return <QueuedConfirmation sessionId={sessionId} />;

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
          Noter la session
        </p>
      </header>

      {/* Le spot en tête, modifiable en un tap : le serveur l'a deviné, et il
          se trompe d'autant plus souvent qu'on est loin de chez soi. */}
      <section className="px-5 pb-5">
        <button
          type="button"
          onClick={() => setSpotPickerOpen((open) => !open)}
          className="flex w-full items-center gap-3 text-left"
        >
          <IconPin className="h-6 w-6 shrink-0 text-mute" />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-display text-[30px] font-bold leading-none uppercase tracking-tight text-ink">
              {chosenSpot?.name ?? "Spot inconnu"}
            </span>
            <span className="mt-1.5 block text-[13px] text-mute">
              {shortDate(data.started_at)} · appuie pour changer
            </span>
          </span>
          <IconChevronDown
            className={`h-5 w-5 shrink-0 text-mute transition-transform ${
              spotPickerOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {spotPickerOpen ? (
          <ul className="mt-3 overflow-hidden rounded-card border border-line bg-card">
            {(nearby.data ?? []).slice(0, SPOT_CHOICES).map((option) => (
              <li key={option.id} className="border-b border-line last:border-0">
                <button
                  type="button"
                  onClick={() => {
                    setSpotId(option.id);
                    setSpotPickerOpen(false);
                  }}
                  className="flex min-h-touch w-full items-center gap-3 px-4 py-2.5 text-left"
                >
                  <span
                    className={`min-w-0 flex-1 truncate text-[15px] font-semibold ${
                      option.id === spotId ? "text-accent" : "text-ink"
                    }`}
                  >
                    {option.name}
                  </span>
                  <span className="tabular shrink-0 text-[12px] text-mute">
                    {distanceLabel(option.distance_km)}
                  </span>
                </button>
              </li>
            ))}
            {nearby.isPending ? (
              <li className="px-4 py-3 text-[14px] text-mute">Recherche…</li>
            ) : null}
            {!nearby.isPending && (nearby.data ?? []).length === 0 ? (
              <li className="px-4 py-3 text-[14px] text-ink-2">
                Aucun autre spot à proximité.
              </li>
            ) : null}
          </ul>
        ) : null}
      </section>

      <Section title="Horaire">
        <div className="flex gap-3">
          <TimeWheel label="Début" value={start} onChange={setStart} max={end} />
          <TimeWheel label="Fin" value={end} onChange={setEnd} min={start} />
        </div>
        <p className="tabular mt-2.5 text-[14px] text-ink-2">
          {durationLabel(durationMin)} à l&apos;eau
          {data.start_estimated ? (
            <span className="text-mute"> · début estimé, corrige si besoin</span>
          ) : null}
        </p>
      </Section>

      {/* Les deux notes, séparées visuellement par un filet et un fond : les
          confondre est l'erreur que la double note existe pour empêcher. */}
      <Section>
        <RatingScale
          name="Qualité des conditions"
          label="Qualité des conditions"
          hint="la mer"
          value={conditions}
          onChange={setConditions}
        />
      </Section>

      <section className="border-t border-line bg-soft px-5 py-5">
        <RatingScale
          name="Mon ressenti"
          label="Mon ressenti"
          hint="la forme du jour"
          value={personal}
          onChange={setPersonal}
        />
      </section>

      <Section title="Planche">
        {boards.length === 0 ? (
          <p className="text-[14px] text-ink-2">
            Pas encore de planche.{" "}
            <button
              type="button"
              onClick={() => router.push("/surf/matos")}
              className="font-semibold text-accent underline"
            >
              Ajoute ton matos
            </button>
            .
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {boards.map((board) => {
              const selected = board.id === gearId;
              return (
                <button
                  key={board.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setGearChoice(selected ? null : board.id)}
                  className={`flex min-h-touch items-center gap-2 rounded-pill border px-4 text-[15px] font-semibold ${
                    selected
                      ? "border-accent bg-accent text-on-accent"
                      : "border-line bg-card text-ink-2"
                  }`}
                >
                  <IconBoard className="h-4 w-4 shrink-0" />
                  {board.name}
                  {board.length_m !== null ? (
                    <span className="tabular opacity-70">
                      {boardLength(board.length_m)}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        )}
      </Section>

      <Section>
        <WaveStepper value={waves} onChange={setWaves} />
      </Section>

      {/* Note libre et photo : repliées, et elles le restent tant qu'on ne les
          demande pas. C'est le seul endroit de l'écran où un clavier peut
          apparaître, et il faut un tap délibéré pour cela. */}
      <Section>
        <button
          type="button"
          onClick={() => setExtrasOpen((open) => !open)}
          aria-expanded={extrasOpen}
          className="flex min-h-touch w-full items-center justify-between gap-3 text-left"
        >
          <span className="text-[15px] font-semibold text-ink-2">
            Note libre et photo
          </span>
          <IconChevronDown
            className={`h-5 w-5 shrink-0 text-mute transition-transform ${
              extrasOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {extrasOpen ? (
          <div className="mt-3 flex flex-col gap-3">
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              placeholder="Ce dont tu veux te souvenir"
              aria-label="Note libre"
              className="w-full rounded-button border border-line bg-card px-3 py-2.5 text-[16px] text-ink placeholder:text-mute"
            />

            <input
              ref={photoInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) photo.mutate(file);
                event.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => photoInput.current?.click()}
              disabled={photo.isPending}
              className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2 disabled:opacity-50"
            >
              <IconCamera className="h-5 w-5" />
              {photo.isPending
                ? "Envoi…"
                : data.photo_url
                  ? "Remplacer la photo"
                  : "Ajouter une photo"}
            </button>
            {photo.error ? (
              <p className="text-[13px] text-ink-2">
                {photo.error instanceof ApiError && photo.error.status === 0
                  ? "Photo impossible sans réseau — la note, elle, part quand même."
                  : "Photo non enregistrée."}
              </p>
            ) : null}
            {data.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={data.photo_url}
                alt="Photo de la session"
                className="w-full rounded-card border border-line"
              />
            ) : null}
          </div>
        ) : null}
      </Section>

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
              spot_id: spotId ?? data.spot_id,
              started_at: start.toISOString(),
              duration_min: Math.max(15, durationMin),
              rating_conditions: conditions as number,
              rating_personal: personal as number,
              ...(gearId !== null ? { gear_id: gearId } : {}),
              wave_count: waves,
              notes: notes.trim() || null,
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
