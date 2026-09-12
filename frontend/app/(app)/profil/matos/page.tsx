"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { IconBack, IconBoard, IconPlus, IconTrash } from "@/components/ui/Icons";
import { ApiError, api } from "@/lib/api";
import { boardLength, lengthFromFeet, num, shortDate } from "@/lib/format";
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
 */

const FEET = [4, 5, 6, 7, 8, 9, 10] as const;
const INCHES = [0, 2, 4, 6, 8, 10] as const;
const VOLUMES = [24, 26, 28, 30, 32, 35, 40, 50, 65] as const;

const TYPE_LABELS: Record<GearType, string> = {
  board: "Planche",
  wetsuit: "Combinaison",
  accessory: "Accessoire",
};

function Wheel<T extends number>({
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

function GearCard({ gear }: { gear: GearWithUsage }) {
  const queryClient = useQueryClient();
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

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className="min-h-touch flex-1 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2 disabled:opacity-50"
        >
          {gear.is_active ? "Ranger" : "Remettre en service"}
        </button>
        {confirming ? (
          <>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-touch rounded-button border border-line bg-card px-3 text-[14px] font-semibold text-ink-2"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              className="min-h-touch rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink disabled:opacity-50"
            >
              Confirmer
            </button>
          </>
        ) : (
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
        )}
      </div>
    </article>
  );
}

function NewGearForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<GearType>("board");
  const [feet, setFeet] = useState<number | null>(6);
  const [inches, setInches] = useState<number | null>(2);
  const [volume, setVolume] = useState<number | null>(30);

  const create = useMutation({
    mutationFn: () =>
      api.createGear({
        name: name.trim(),
        gear_type: type,
        discipline: "surf" as Discipline,
        length_m:
          type === "board" && feet !== null && inches !== null
            ? lengthFromFeet(feet, inches)
            : null,
        volume_l: type === "board" ? volume : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gear"] });
      onDone();
    },
  });

  return (
    <form
      className="flex flex-col gap-4 rounded-card border border-line bg-card px-4 py-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) create.mutate();
      }}
    >
      <div>
        <label
          htmlFor="gear-name"
          className="block pb-1.5 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute"
        >
          Nom court
        </label>
        <input
          id="gear-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="6'2 Pyzel"
          maxLength={40}
          autoComplete="off"
          className="min-h-touch w-full rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
        />
      </div>

      <Wheel
        label="Type"
        options={[0, 1, 2] as const}
        value={(["board", "wetsuit", "accessory"] as GearType[]).indexOf(
          type,
        ) as 0 | 1 | 2}
        onChange={(index) =>
          setType((["board", "wetsuit", "accessory"] as GearType[])[index])
        }
        format={(index) =>
          TYPE_LABELS[(["board", "wetsuit", "accessory"] as GearType[])[index]]
        }
      />

      {type === "board" ? (
        <>
          <div className="flex gap-4">
            <Wheel
              label="Pieds"
              options={FEET}
              value={feet as (typeof FEET)[number] | null}
              onChange={setFeet}
            />
            <Wheel
              label="Pouces"
              options={INCHES}
              value={inches as (typeof INCHES)[number] | null}
              onChange={setInches}
            />
          </div>
          {feet !== null && inches !== null ? (
            <p className="tabular -mt-2 text-[13px] text-mute">
              {feet}&apos;{inches} — stocké {num(lengthFromFeet(feet, inches), 2)} m
            </p>
          ) : null}
          <Wheel
            label="Volume (L)"
            options={VOLUMES}
            value={volume as (typeof VOLUMES)[number] | null}
            onChange={setVolume}
          />
        </>
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
          disabled={!name.trim() || create.isPending}
          className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-40"
        >
          {create.isPending ? "Ajout…" : "Ajouter"}
        </button>
      </div>
    </form>
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
          onClick={() => router.push("/profil")}
          aria-label="Retour au profil"
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Profil
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
          <NewGearForm onDone={() => setAdding(false)} />
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
