"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import {
  DoneSessionRow,
  PendingSessionBlock,
} from "@/components/session/PendingSessionBlock";
import { DailyLogSwipe } from "@/components/surf/DailyLogSwipe";
import { SeaBlock } from "@/components/surf/SeaBlock";
import { IconCloudOff, IconSearch } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { useGeolocation } from "@/lib/useGeolocation";
import { useOfflineQueue } from "@/lib/useOfflineQueue";

/**
 * **Jour** — la journée dans l'ordre où elle se vit.
 *
 * La fenêtre de mer, la séance, les repas, la pesée. Les modules ne sont plus
 * des onglets, ce sont les ingrédients du jour : c'est ce qui rendra visible le
 * lien entre eux — la cible calorique qui monte parce qu'il y a eu 1 h 43 à
 * l'eau, la mobilité proposée après trois jours de surf d'affilée.
 *
 * L'ordre n'est pas figé, il suit l'heure : **une session à noter passe devant
 * tout le reste**. À 11 h, ce qui compte n'est plus la prévision du matin,
 * c'est la session qu'on vient de finir — et une session non notée est une
 * ligne sans étiquette, donc inutile au modèle. Une fois notée, le bloc de mer
 * reprend sa place et la session du jour se range en pied.
 *
 * Le bloc de mer porte **la prévision du spot favori du profil**, et elle
 * seule. Interroger le rayon à chaque ouverture reviendrait à ingérer des spots
 * que personne ne regarde (décidé le 12/09 au soir, cf. PROJET.md §11).
 */

/**
 * Emplacement d'un lot à venir.
 *
 * Il est là pour que la hiérarchie de l'écran soit juste dès maintenant, et il
 * ne promet rien qu'il ne tienne : une ligne sobre, pas un bouton mort qui
 * donne l'impression d'une panne.
 */
function ComingSlot({ title, hint, lot }: { title: string; hint: string; lot: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-card border border-line bg-card px-4 py-3">
      <div className="min-w-0">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-mute">
          {title}
        </p>
        <p className="mt-0.5 truncate text-[14px] text-ink-2">{hint}</p>
      </div>
      <span className="shrink-0 rounded-pill border border-line bg-soft px-2.5 py-1 text-[12px] font-semibold text-mute">
        {lot}
      </span>
    </div>
  );
}

export default function JourPage() {
  const geolocation = useGeolocation();
  const offline = useOfflineQueue();

  const { data, isPending, error, isFetching } = useQuery({
    // La position fait partie de la clé : changer de coin met la distance à jour.
    queryKey: ["recommend", geolocation.position],
    queryFn: () => api.recommend(geolocation.position),
    // On attend la géoloc, mais pas éternellement : dès qu'elle est tranchée
    // (acceptée, refusée ou indisponible), on interroge le back, qui se rabat
    // sur le domicile puis sur le spot favori.
    enabled: geolocation.status !== "pending",
    // Le back complète parfois en arrière-plan : on retente une fois.
    refetchInterval: (query) =>
      query.state.data?.refreshing.length ? 6_000 : false,
  });

  // Un seul aller-retour pour les deux questions de l'écran : « y a-t-il une
  // session à noter ? » et « qu'est-ce que j'ai fait aujourd'hui ? ».
  const journal = useQuery({
    queryKey: ["session-journal"],
    queryFn: api.sessionJournal,
  });

  const toRate = journal.data?.to_rate ?? [];
  const doneToday = (journal.data?.today ?? []).filter(
    (session) => session.status === "rated",
  );

  if (geolocation.status === "pending" || isPending) {
    return (
      <main className="flex min-h-[60vh] flex-col items-center justify-center gap-2 px-5">
        <p className="font-display text-[22px] text-ink-2">Je regarde la mer…</p>
        <p className="text-[13px] text-mute">
          {geolocation.status === "pending"
            ? "Localisation en cours"
            : "Prévisions en cours de lecture"}
        </p>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="px-5 py-10 text-center">
        <p className="text-[16px] text-ink">Prévisions indisponibles.</p>
        <p className="mt-2 text-[14px] text-mute">
          Réessaie quand le réseau revient.
        </p>
      </main>
    );
  }

  return (
    <main className="flex flex-col gap-4 pb-6 pt-5">
      {/* Devant tout le reste tant qu'elle n'est pas notée. */}
      {toRate.map((session) => (
        <PendingSessionBlock key={session.id} session={session} />
      ))}

      {data.home_spot ? (
        <SeaBlock data={data} />
      ) : (
        /* Sans favori, l'app ne choisit pas à la place de Jules : elle ne va
           pas non plus chercher la prévision de quinze spots pour meubler. */
        <section className="px-5">
          <article className="rounded-card border border-line bg-card px-5 py-6">
            <h2 className="font-display text-[26px] leading-none font-semibold uppercase text-ink">
              Choisis ton spot
            </h2>
            <p className="mt-3 text-[15px] leading-snug text-ink-2">
              Jour affiche la prévision d&apos;un seul spot : le tien. Les autres
              se consultent depuis Surf, quand tu les regardes.
            </p>
            <Link
              href="/surf"
              className="mt-4 flex min-h-touch items-center justify-center gap-2 rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent"
            >
              <IconSearch className="h-5 w-5" />
              Chercher un spot
            </Link>
          </article>
        </section>
      )}

      <DailyLogSwipe />

      <section className="flex flex-col gap-3 px-5" aria-label="Le reste de la journée">
        <ComingSlot
          title="Séance"
          hint="Mobilité, renfo, gainage"
          lot="lot 4"
        />
        <ComingSlot
          title="Repas"
          hint="Cible calorique et journal"
          lot="lot 5"
        />
      </section>

      {/* La journée telle qu'elle s'est passée, en pied : un rappel, pas une
          action. */}
      {doneToday.length > 0 ? (
        <section className="flex flex-col gap-2 px-5" aria-label="Sessions du jour">
          {doneToday.map((session) => (
            <DoneSessionRow key={session.id} session={session} />
          ))}
        </section>
      ) : null}

      {offline.pending > 0 ? (
        <p className="flex items-center gap-2 px-5 text-[12px] text-mute">
          <IconCloudOff className="h-4 w-4 shrink-0" />
          {offline.pending} notation(s) en attente d&apos;envoi
        </p>
      ) : null}

      {isFetching || data.refreshing.length > 0 ? (
        <p className="px-5 text-[12px] text-mute">
          Mise à jour des prévisions en cours…
        </p>
      ) : null}
    </main>
  );
}
