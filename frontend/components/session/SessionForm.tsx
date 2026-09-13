"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { DateWheel } from "@/components/session/DateWheel";
import { RatingScale } from "@/components/session/RatingScale";
import { SegmentRating } from "@/components/session/SegmentRating";
import { TimeWheel } from "@/components/session/TimeWheel";
import { WaveStepper } from "@/components/session/WaveStepper";
import { WaveTypeFields } from "@/components/session/WaveTypeFields";
import { SpotPicker } from "@/components/surf/SpotPicker";
import {
  IconBoard,
  IconCamera,
  IconChevronDown,
  IconPin,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { boardLength, durationLabel, minutesBetween } from "@/lib/format";
import type {
  Gear,
  SessionSegmentValue,
  SpotHit,
  WaveType,
} from "@/lib/types";

/**
 * Le formulaire de session — **un seul**, pour la notation et la création.
 *
 * Depuis le 13/09, une session se crée et se corrige **depuis le navigateur**,
 * pas seulement par le raccourci iPhone. Les deux écrans partagent ce
 * composant, et ce n'est pas qu'une économie de lignes : deux formulaires
 * divergeraient, et une session saisie à la main finirait par ne plus porter
 * les mêmes champs qu'une session notée — c'est-à-dire deux lignes
 * d'apprentissage de forme différente.
 *
 * Les règles d'ergonomie du lot 2 tiennent, toutes :
 *
 * - **aucune zone de texte visible sans une action explicite.** La note libre
 *   et la photo sont repliées en bas. Un champ de texte visible attire le
 *   doigt, ouvre le clavier, mange la moitié de l'écran ;
 * - **molettes et boutons**, jamais de sélecteur natif : le rouleau modal
 *   d'iOS demande deux taps et recouvre l'écran ;
 * - **les deux notes, jamais une seule.** Le bouton reste inerte tant qu'il en
 *   manque une (`CLAUDE.md`, règle 6).
 *
 * Ce qui change entre les deux usages tient dans les props : la création
 * montre la date en molette dès l'ouverture et cherche dans tout le catalogue,
 * la notation propose d'abord les cinq spots les plus proches du point
 * d'entrée à l'eau — le serveur a deviné, et il se trompe d'autant plus qu'on
 * est loin de chez soi.
 */

export interface SessionFormValues {
  spotId: number | null;
  start: Date;
  end: Date;
  conditions: number | null;
  personal: number | null;
  /** `undefined` = pas encore touché, l'appelant applique son défaut ;
   *  `null` = explicitement aucune planche. Les deux ne veulent pas dire la
   *  même chose, et les confondre effacerait un choix. */
  gearId: number | null | undefined;
  waves: number;
  notes: string;
  /** Les notes heure par heure, optionnelles. Vide = pas de détail. */
  segments: SessionSegmentValue[];
  /** Taille, longueur, forme. Tout optionnel : « non renseigné » n'est pas
   *  « moyen », et le confondre fabriquerait une observation que personne n'a
   *  faite. */
  waveType: WaveType;
}

interface SessionFormProps {
  values: SessionFormValues;
  onChange: (next: SessionFormValues) => void;
  /** Nom du spot courant, quand l'appelant le connaît déjà. */
  spotName: string | null;
  /** Les spots proposés en premier — les plus proches, sur l'écran de notation. */
  suggestions?: SpotHit[];
  suggestionsPending?: boolean;
  /** Vrai sur l'écran de création : la date se règle dès l'ouverture. */
  showDate?: boolean;
  /** Mention sous le nom du spot — « début estimé », par exemple. */
  hint?: string;
  /** Bloc photo, rendu par l'appelant : il n'existe qu'une fois la session
   *  créée, donc jamais sur l'écran de création. */
  photoSlot?: React.ReactNode;
}

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

/** Déplace un instant sur un autre jour, en gardant son heure. */
function withDay(instant: Date, day: Date): Date {
  const next = new Date(instant);
  next.setFullYear(day.getFullYear(), day.getMonth(), day.getDate());
  return next;
}

export function SessionForm({
  values,
  onChange,
  spotName,
  suggestions,
  suggestionsPending = false,
  showDate = false,
  hint,
  photoSlot,
}: SessionFormProps) {
  const [spotOpen, setSpotOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [waveTypeOpen, setWaveTypeOpen] = useState(false);
  const [pickedName, setPickedName] = useState<string | null>(null);

  const gear = useQuery({
    queryKey: ["gear", "active"],
    queryFn: () => api.gear(false),
  });

  const boards: Gear[] = useMemo(
    () => (gear.data ?? []).filter((item) => item.gear_type === "board"),
    [gear.data],
  );

  const set = (patch: Partial<SessionFormValues>) =>
    onChange({ ...values, ...patch });

  const durationMin = minutesBetween(values.start, values.end);

  const name =
    pickedName ??
    suggestions?.find((hit) => hit.id === values.spotId)?.name ??
    spotName ??
    "Choisis un spot";

  /**
   * Changer de jour déplace le début **et** la fin ensemble.
   *
   * Sinon une session de 8 h à 9 h 30 devient une session de 8 h le mardi à
   * 9 h 30 le lundi, c'est-à-dire une durée négative — et l'écran afficherait
   * « −22 h à l'eau » sans qu'on comprenne pourquoi.
   */
  const moveToDay = (day: Date) => {
    const start = withDay(values.start, day);
    const minutes = minutesBetween(values.start, values.end);
    set({ start, end: new Date(start.getTime() + minutes * 60_000) });
  };

  return (
    <>
      {/* Le spot en tête : c'est la première chose qu'on corrige, et sur la
          création c'est la première qu'on choisit. */}
      <section className="px-5 pb-5">
        <button
          type="button"
          onClick={() => setSpotOpen((open) => !open)}
          aria-expanded={spotOpen}
          className="flex w-full items-center gap-3 text-left"
        >
          <IconPin className="h-6 w-6 shrink-0 text-mute" />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-display text-[30px] font-bold leading-none uppercase tracking-tight text-ink">
              {name}
            </span>
            <span className="mt-1.5 block text-[13px] text-mute">
              {hint ?? "appuie pour changer"}
            </span>
          </span>
          <IconChevronDown
            className={`h-5 w-5 shrink-0 text-mute transition-transform ${
              spotOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {spotOpen ? (
          <div className="mt-3">
            {/* Les suggestions d'abord — elles sont justes neuf fois sur dix
                et ne coûtent qu'un tap. La recherche est le recours. */}
            {!searchOpen && suggestions && suggestions.length > 0 ? (
              <ul className="overflow-hidden rounded-card border border-line bg-card">
                {suggestions.map((option) => (
                  <li
                    key={option.id}
                    className="border-b border-line last:border-0"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        set({ spotId: option.id });
                        setPickedName(option.name);
                        setSpotOpen(false);
                      }}
                      className="flex min-h-touch w-full items-center gap-3 px-4 py-2.5 text-left"
                    >
                      <span
                        className={`min-w-0 flex-1 truncate text-[15px] font-semibold ${
                          option.id === values.spotId ? "text-accent" : "text-ink"
                        }`}
                      >
                        {option.name}
                      </span>
                      {option.distance_km !== null ? (
                        <span className="tabular shrink-0 text-[12px] text-mute">
                          {option.distance_km < 10
                            ? `${option.distance_km.toFixed(1).replace(".", ",")} km`
                            : `${Math.round(option.distance_km)} km`}
                        </span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            {suggestionsPending && !searchOpen ? (
              <p className="px-1 py-2 text-[14px] text-mute">Recherche…</p>
            ) : null}

            {searchOpen ? (
              <div className="-mx-5">
                <SpotPicker
                  selectedId={values.spotId}
                  onSelect={(_slug, hit) => {
                    set({ spotId: hit.id });
                    setPickedName(hit.name);
                    setSearchOpen(false);
                    setSpotOpen(false);
                  }}
                  onClose={() => setSearchOpen(false)}
                />
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setSearchOpen(true)}
                className="mt-2 flex min-h-touch w-full items-center justify-center rounded-button border border-line bg-card px-4 text-[14px] font-semibold text-ink-2"
              >
                Chercher dans tout le catalogue
              </button>
            )}
          </div>
        ) : null}
      </section>

      <Section title={showDate ? "Quand" : "Horaire"}>
        {showDate ? (
          <div className="pb-3">
            <DateWheel value={values.start} onChange={moveToDay} />
          </div>
        ) : null}
        <div className="flex gap-3">
          <TimeWheel
            label="Début"
            value={values.start}
            onChange={(start) => set({ start })}
            max={values.end}
          />
          <TimeWheel
            label="Fin"
            value={values.end}
            onChange={(end) => set({ end })}
            min={values.start}
          />
        </div>
        <p className="tabular mt-2.5 text-[14px] text-ink-2">
          {durationLabel(durationMin)} à l&apos;eau
        </p>
      </Section>

      {/* Les deux notes, séparées par un filet et un fond : les confondre est
          l'erreur que la double note existe pour empêcher. */}
      <Section>
        <RatingScale
          name="Qualité des conditions"
          label="Qualité des conditions"
          hint="la mer"
          value={values.conditions}
          onChange={(conditions) => set({ conditions })}
        />
      </Section>

      <section className="border-t border-line bg-soft px-5 py-5">
        <RatingScale
          name="Mon ressenti"
          label="Mon ressenti"
          hint="la forme du jour"
          value={values.personal}
          onChange={(personal) => set({ personal })}
        />
      </section>

      {/* Le détail horaire, replié et discret : le chemin normal reste deux
          taps. Il n'apparaît qu'au-delà d'une heure — en dessous, ce serait la
          note globale écrite deux fois. */}
      <SegmentRating
        start={values.start}
        end={values.end}
        conditions={values.conditions}
        personal={values.personal}
        segments={values.segments}
        onChange={(segments) => set({ segments })}
      />

      <Section title="Planche">
        {boards.length === 0 ? (
          <p className="text-[14px] text-ink-2">
            Pas encore de planche enregistrée. Le matos se saisit depuis Surf.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {boards.map((board) => {
              const selected = board.id === values.gearId;
              return (
                <button
                  key={board.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => set({ gearId: selected ? null : board.id })}
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
        <WaveStepper value={values.waves} onChange={(waves) => set({ waves })} />
      </Section>

      {/* Trois axes optionnels, repliés : ils décrivent ce que les
          instruments ne mesurent pas, et ils ne rallongent pas le chemin des
          quinze secondes tant qu'on ne les ouvre pas. */}
      <Section>
        <WaveTypeFields
          value={values.waveType}
          onChange={(waveType) => set({ waveType })}
          open={waveTypeOpen}
          onToggle={() => setWaveTypeOpen((open) => !open)}
        />
      </Section>

      {/* Le seul endroit de l'écran où un clavier peut apparaître, et il faut
          un tap délibéré pour cela. */}
      <Section>
        <button
          type="button"
          onClick={() => setExtrasOpen((open) => !open)}
          aria-expanded={extrasOpen}
          className="flex min-h-touch w-full items-center justify-between gap-3 text-left"
        >
          <span className="text-[15px] font-semibold text-ink-2">
            Note libre{photoSlot ? " et photo" : ""}
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
              value={values.notes}
              onChange={(event) => set({ notes: event.target.value })}
              rows={3}
              placeholder="Ce dont tu veux te souvenir"
              aria-label="Note libre"
              className="w-full rounded-button border border-line bg-card px-3 py-2.5 text-[16px] text-ink placeholder:text-mute"
            />
            {photoSlot}
          </div>
        ) : null}
      </Section>
    </>
  );
}

/** Le bouton photo, rendu à part : il n'existe qu'une fois la session créée. */
export function PhotoField({
  hasPhoto,
  pending,
  onPick,
  error,
  url,
}: {
  hasPhoto: boolean;
  pending: boolean;
  onPick: (file: File) => void;
  error?: string | null;
  url?: string | null;
}) {
  const input = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onPick(file);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={pending}
        className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2 disabled:opacity-50"
      >
        <IconCamera className="h-5 w-5" />
        {pending ? "Envoi…" : hasPhoto ? "Remplacer la photo" : "Ajouter une photo"}
      </button>
      {error ? <p className="text-[13px] text-ink-2">{error}</p> : null}
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt="Photo de la session"
          className="w-full rounded-card border border-line"
        />
      ) : null}
    </>
  );
}
