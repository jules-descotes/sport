"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import {
  DoneSessionRow,
  PendingSessionBlock,
} from "@/components/session/PendingSessionBlock";
import { Freshness, PullToRefresh } from "@/components/shell/Freshness";
import { HabitRow } from "@/components/habits/HabitRow";
import { DayMealBlock } from "@/components/nutrition/DayMealBlock";
import { DailyLogSwipe } from "@/components/surf/DailyLogSwipe";
import { MatchAnnouncements } from "@/components/surf/MatchAnnouncements";
import { DayExpenditure } from "@/components/nutrition/DayExpenditure";
import { DayProposal } from "@/components/training/DayProposal";
import { SeaBlock } from "@/components/surf/SeaBlock";
import { IconCloudOff, IconPlus, IconSearch } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { forecastKey } from "@/lib/forecast-cache";
import type { Recommendation } from "@/lib/types";
import { useCachedForecast } from "@/lib/useCachedForecast";
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
 *
 * **Desktop** (décidé le 13/09) : trois colonnes — la mer, ce qu'on fait, ce
 * qu'on note. L'ordre vertical du mobile devient un ordre de gauche à droite,
 * et rien ne change de sens : on lit toujours la mer d'abord.
 */

export default function JourPage() {
  const geolocation = useGeolocation();
  const offline = useOfflineQueue();

  const forecast = useCachedForecast<Recommendation>({
    // Une seule entrée : Jour ne montre que le favori, quelle que soit la
    // position. Celle-ci ne change que les distances affichées.
    cacheKey: forecastKey("recommend"),
    // La position fait partie de la clé de requête : changer de coin met la
    // distance à jour.
    queryKey: ["recommend", geolocation.position],
    queryFn: () => api.recommend(geolocation.position),
    runTs: (data) => data.run_ts,
    // On attend la géoloc, mais pas éternellement : dès qu'elle est tranchée
    // (acceptée, refusée ou indisponible), on interroge le back, qui se rabat
    // sur le domicile puis sur le spot favori.
    enabled: geolocation.status !== "pending",
    // Le back complète parfois en arrière-plan : on retente tant qu'il le dit.
    keepPolling: (data) => data.refreshing.length > 0,
  });
  const data = forecast.data;

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

  if (geolocation.status === "pending" || forecast.isPending) {
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

  if (forecast.error || !data) {
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
      <PullToRefresh onRefresh={forecast.refresh} />

      {/* Devant tout le reste tant qu'elle n'est pas notée, et sur toute la
          largeur : c'est la seule chose à faire à cet instant. */}
      {toRate.map((session) => (
        <PendingSessionBlock key={session.id} session={session} />
      ))}

      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,0.85fr)] lg:items-start lg:gap-0">
        {/* ── La mer ──────────────────────────────────────────────────── */}
        <div className="flex flex-col gap-2">
          {data.home_spot ? (
            <SeaBlock data={data} />
          ) : (
            /* Sans favori, l'app ne choisit pas à la place de Jules : elle ne
               va pas non plus chercher la prévision de quinze spots pour
               meubler. */
            <section className="px-5">
              <article className="rounded-card border border-line bg-card px-5 py-6">
                <h2 className="font-display text-[26px] leading-none font-semibold uppercase text-ink">
                  Choisis ton spot
                </h2>
                <p className="mt-3 text-[15px] leading-snug text-ink-2">
                  Jour affiche la prévision d&apos;un seul spot : le tien. Les
                  autres se consultent depuis Surf, quand tu les regardes.
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

          {/* Les autres favoris qui devraient marcher, d'après ses critères.
              Sous le bloc de mer : c'est une information secondaire, et Jour
              n'a qu'une seule information en grand. */}
          <MatchAnnouncements matches={data.matches} />

          <Freshness
            className="px-5"
            cachedAt={forecast.cachedAt}
            isFetching={forecast.isFetching}
            refreshing={data.refreshing.length > 0}
            onRefresh={forecast.refresh}
          />
        </div>

        {/* ── Ce qu'on fait ───────────────────────────────────────────── */}
        <section
          className="flex flex-col gap-3 px-5"
          aria-label="Le reste de la journée"
        >
          {/* La séance du jour, lançable sur place : partir sur Training,
              choisir, revenir, ce sont trois écrans pour un geste qui en vaut
              zéro. */}
          <DayProposal />
          {/* Les repas : la jauge du jour, le plat prévu, et la saisie sur
              place. Un repas se note au moment où on le mange, pas au moment
              où on ouvre le bon onglet. */}
          <DayMealBlock />
          {/* Ce que la journée a coûté, en un chiffre et un mot :
              « estimation ». Elle est sous ce qu'on fait et pas au-dessus —
              c'est un constat de fin de journée, pas une consigne du matin
              (décidé le 13/09). Absente tant qu'il n'y a rien à compter : une
              ligne « 0 kcal » serait un reproche. */}
          <DayExpenditure />

          {/* Le raccourci iPhone reste le chemin normal ; celui-ci rattrape
              les sessions qu'il a manquées — téléphone resté dans la voiture,
              session d'il y a trois semaines. Discret : ce n'est pas le geste
              du matin (décidé le 13/09). */}
          <Link
            href="/sessions/nouvelle"
            className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[14px] font-semibold text-ink-2"
          >
            <IconPlus className="h-5 w-5" />
            Ajouter une session
          </Link>
        </section>

        {/* ── Ce qu'on note ───────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <DailyLogSwipe />

          {/* Les compteurs libres, en un tap. Ton strictement neutre : une
              habitude atteinte passe en accent, une habitude non atteinte
              reste neutre — il n'y a pas de troisième état (décidé le
              13/09). */}
          <HabitRow />

          {/* La journée telle qu'elle s'est passée : un rappel, pas une
              action. */}
          {doneToday.length > 0 ? (
            <section
              className="flex flex-col gap-2 px-5"
              aria-label="Sessions du jour"
            >
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
        </div>
      </div>
    </main>
  );
}
