"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { SurfTabs } from "@/components/surf/SurfTabs";
import { IconBack, IconBoard, IconPlus, IconTrash } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import { boardLength, num, shortDate } from "@/lib/format";
import {
  FEET,
  GEAR_TYPES,
  INCHES,
  NEW_GEAR,
  VOLUMES,
  draftFromGear,
  draftLength,
  draftVolume,
  gearPatch,
  withValue,
} from "@/lib/gear-form";
import type { GearDraft } from "@/lib/gear-form";
import type { Discipline, GearType, GearWithUsage } from "@/lib/types";

/**
 * **Matos** — planches et combinaisons, et leur usure.
 *
 * La longueur se saisit en **pieds et pouces**, parce que c'est la seule façon
 * dont on parle d'une planche ; elle part en base **en mètres**, parce qu'un
 * 6'2 est une unité composite et que le CLAUDE.md l'interdit. La conversion
 * est un affichage, au même titre que celle des heures UTC en heure locale.
 *
 * Et on ne saisit pas au clavier : des molettes, ici comme partout ailleurs
 * (`PROJET.md` §1, règle 5). Seul le nom — « 6'2 Pyzel » — demande des
 * lettres, et c'est le seul champ texte de l'écran.
 *
 * **Un seul formulaire sert à créer et à corriger.** Deux divergeraient, et
 * une planche corrigée finirait par ne plus porter les mêmes champs qu'une
 * planche créée — la même raison qui fait partager `SessionForm` entre la
 * saisie manuelle et l'écran de notation.
 */

const TYPE_LABELS: Record<GearType, string> = {
  board: "Planche",
  wetsuit: "Combinaison",
  accessory: "Accessoire",
};

function Wheel<T extends string | number>({
  label,
  options,
  value,
  onChange,
  format,
}: {
  label: string;
  options: readonly T[];
  value: T | null;
  onChange: (next: T) => void;
  format?: (value: T) => string;
}) {
  return (
    <div className="min-w-0">
      <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={value === option}
            onClick={() => onChange(option)}
            className={`tabular min-h-touch min-w-[52px] rounded-pill border px-3 text-[15px] font-semibold ${
              value === option
                ? "border-accent bg-accent text-on-accent"
                : "border-line bg-card text-ink-2"
            }`}
          >
            {format ? format(option) : option}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Créer du matos, ou corriger celui qui est déjà là.
 *
 * En correction, **on n'envoie que ce qui a changé**. Un PATCH qui renverrait
 * tous les champs réécrirait la longueur avec ce que la molette sait afficher :
 * une planche entrée à 6'3 repartirait à 6'2 parce qu'on a corrigé son volume.
 */
function GearForm({
  gear,
  onDone,
}: {
  gear?: GearWithUsage;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<GearDraft>(() =>
    gear ? draftFromGear(gear) : NEW_GEAR,
  );
  const [failure, setFailure] = useState<string | null>(null);

  const set = <K extends keyof GearDraft>(key: K, value: GearDraft[K]) =>
    setDraft((previous) => ({ ...previous, [key]: value }));

  const name = draft.name.trim();
  const length = draftLength(draft);
  const patch = gear ? gearPatch(gear, draft) : null;
  // Rien de changé, rien à enregistrer : le bouton reste inerte plutôt que de
  // faire semblant.
  const changed = patch === null || Object.keys(patch).length > 0;

  const save = useMutation({
    mutationFn: () => {
      if (gear === undefined) {
        return api.createGear({
          name,
          gear_type: draft.type,
          discipline: "surf" as Discipline,
          length_m: length,
          volume_l: draftVolume(draft),
        });
      }
      return api.updateGear(gear.id, patch ?? {});
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gear"] });
      onDone();
    },
    onError: (error) => {
      setFailure(
        error instanceof ApiError ? error.message : "Enregistrement impossible.",
      );
    },
  });

  return (
    <form
      className="flex flex-col gap-4 rounded-card border border-line bg-card px-4 py-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (name && changed) {
          setFailure(null);
          save.mutate();
        }
      }}
    >
      <div>
        <label
          htmlFor={`gear-name-${gear?.id ?? "new"}`}
          className="block pb-1.5 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute"
        >
          Nom court
        </label>
        <input
          id={`gear-name-${gear?.id ?? "new"}`}
          value={draft.name}
          onChange={(event) => set("name", event.target.value)}
          placeholder="6'2 Pyzel"
          maxLength={40}
          autoComplete="off"
          className="min-h-touch w-full rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
        />
      </div>

      <Wheel
        label="Type"
        options={GEAR_TYPES}
        value={draft.type}
        onChange={(option) => set("type", option)}
        format={(option) => TYPE_LABELS[option]}
      />

      {draft.type === "board" ? (
        <>
          <div className="flex gap-4">
            <Wheel
              label="Pieds"
              options={withValue(FEET, draft.feet)}
              value={draft.feet}
              onChange={(option) => set("feet", option)}
            />
            <Wheel
              label="Pouces"
              options={withValue(INCHES, draft.inches)}
              value={draft.inches}
              onChange={(option) => set("inches", option)}
            />
          </div>
          {length !== null ? (
            <p className="tabular -mt-2 text-[13px] text-mute">
              {draft.feet}&apos;{draft.inches} — stocké {num(length, 2)} m
            </p>
          ) : null}
          <Wheel
            label="Volume (L)"
            options={withValue(VOLUMES, draft.volume)}
            value={draft.volume}
            onChange={(option) => set("volume", option)}
          />
        </>
      ) : null}

      {failure ? (
        <p className="rounded-chip bg-soft px-3 py-2 text-[13px] leading-snug text-ink-2">
          {failure}
        </p>
      ) : null}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onDone}
          className="min-h-touch flex-1 rounded-button border border-line bg-soft px-4 text-[15px] font-semibold text-ink-2"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={!name || !changed || save.isPending}
          className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-40"
        >
          {save.isPending
            ? "Enregistrement…"
            : gear
              ? "Enregistrer"
              : "Ajouter"}
        </button>
      </div>
    </form>
  );
}

function GearCard({ gear }: { gear: GearWithUsage }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["gear"] });
  };

  const toggle = useMutation({
    mutationFn: () => api.updateGear(gear.id, { is_active: !gear.is_active }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: () => api.deleteGear(gear.id),
    onSuccess: () => {
      setConfirming(false);
      invalidate();
    },
    onError: (error) => {
      setConfirming(false);
      // 409 : du matos qui a servi ne se supprime pas — le lien session ↔
      // planche est de la donnée d'apprentissage. Le back dit quoi faire.
      setRefusal(
        error instanceof ApiError
          ? error.message
          : "Suppression impossible.",
      );
    },
  });

  if (editing) {
    return <GearForm gear={gear} onDone={() => setEditing(false)} />;
  }

  return (
    <article
      className={`rounded-card border border-line bg-card px-4 py-3 ${
        gear.is_active ? "" : "opacity-60"
      }`}
    >
      <div className="flex items-start gap-3">
        <IconBoard className="mt-0.5 h-5 w-5 shrink-0 text-mute" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[16px] font-semibold text-ink">
            {gear.name}
          </p>
          <p className="tabular mt-0.5 text-[13px] text-mute">
            {[
              TYPE_LABELS[gear.gear_type],
              gear.length_m ? boardLength(gear.length_m) : null,
              gear.volume_l ? `${num(gear.volume_l, 0)} L` : null,
              gear.purchased_on ? `depuis ${shortDate(gear.purchased_on)}` : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className="tabular mt-1 text-[13px] font-semibold text-ink-2">
            {gear.session_count} session{gear.session_count > 1 ? "s" : ""}
            {gear.last_used_at
              ? ` · dernière le ${shortDate(gear.last_used_at)}`
              : ""}
          </p>
        </div>
      </div>

      {refusal ? (
        <p className="mt-2 rounded-chip bg-soft px-3 py-2 text-[13px] leading-snug text-ink-2">
          {refusal}
        </p>
      ) : null}

      {confirming ? (
        <>
          <p className="mt-3 text-[14px] leading-snug text-ink-2">
            {gear.session_count > 0
              ? `${gear.name} porte ${gear.session_count} session${
                  gear.session_count > 1 ? "s" : ""
                } : la suppression sera refusée. Range-le plutôt.`
              : `Supprimer ${gear.name} ? Aucune session n'y est rattachée.`}
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-touch flex-1 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              className="min-h-touch flex-1 rounded-button border border-line bg-card px-3 text-[14px] font-semibold text-ink disabled:opacity-50"
            >
              Supprimer
            </button>
          </div>
        </>
      ) : (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => {
              setRefusal(null);
              setEditing(true);
            }}
            className="min-h-touch flex-1 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2"
          >
            Modifier
          </button>
          <button
            type="button"
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            className="min-h-touch flex-1 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2 disabled:opacity-50"
          >
            {gear.is_active ? "Ranger" : "Ressortir"}
          </button>
          <button
            type="button"
            onClick={() => {
              setRefusal(null);
              setConfirming(true);
            }}
            aria-label={`Supprimer ${gear.name}`}
            className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button border border-line bg-card text-mute"
          >
            <IconTrash className="h-4 w-4" />
          </button>
        </div>
      )}
    </article>
  );
}

export default function MatosPage() {
  const router = useRouter();
  const [adding, setAdding] = useState(false);

  const { data, isPending } = useQuery({
    queryKey: ["gear", "all"],
    queryFn: () => api.gear(true),
  });

  return (
    <main className="pb-10">
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <button
          type="button"
          onClick={() => router.push("/surf")}
          aria-label="Retour à Surf"
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Surf
        </p>
      </header>

      <section className="px-5 pb-5">
        <h1 className="font-display text-[32px] font-bold leading-none uppercase tracking-tight text-ink">
          Matos
        </h1>
        <p className="mt-2 text-[14px] text-ink-2">
          La dernière planche utilisée est proposée d&apos;office quand tu notes
          une session.
        </p>
      </section>

      <SurfTabs />

      <section className="flex flex-col gap-3 px-5">
        {isPending ? (
          <p className="text-[14px] text-mute">Chargement…</p>
        ) : (data ?? []).length === 0 && !adding ? (
          <p className="rounded-card border border-dashed border-line bg-soft px-4 py-4 text-[14px] leading-snug text-ink-2">
            Pas encore de matos. Sans planche, la reco ne pourra jamais dire
            laquelle prendre — c&apos;est une des choses qu&apos;elle sortira au
            lot 3.
          </p>
        ) : (
          (data ?? []).map((gear) => <GearCard key={gear.id} gear={gear} />)
        )}

        {adding ? (
          <GearForm onDone={() => setAdding(false)} />
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
          >
            <IconPlus className="h-5 w-5" />
            Ajouter du matos
          </button>
        )}
      </section>
    </main>
  );
}
