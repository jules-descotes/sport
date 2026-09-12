"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { SessionRow } from "@/components/session/SessionRow";
import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { SurfTabs } from "@/components/surf/SurfTabs";
import { IconCloudOff } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { useOfflineQueue } from "@/lib/useOfflineQueue";

/**
 * **Historique** — liste dense, la plus récente en haut.
 *
 * Volontairement minimal : l'analyse est le lot 6, et c'est elle qui dira
 * « tes meilleures sessions : houle 1,2–1,8 m, période 11–14 s, marée
 * montante » (`PROJET.md` §10.8). Ici on retrouve une journée, on ouvre son
 * détail, et on note ce qui ne l'est pas — rien de plus.
 *
 * L'écran vit sous **Surf** depuis le 13/09 : tout ce qui touche à l'eau
 * entre par la même porte. Les fiches `/sessions/{id}` ne bougent pas — le
 * raccourci iPhone ouvre `/sessions/{id}/noter`, et un lien profond ne se
 * déplace pas.
 */
const PAGE_SIZE = 60;

export default function SessionsPage() {
  const offline = useOfflineQueue();

  const { data, isPending, error } = useQuery({
    queryKey: ["sessions", "history"],
    queryFn: () => api.sessions({ limit: PAGE_SIZE }),
  });

  const pending = (data ?? []).filter(
    (session) => session.status === "to_rate",
  ).length;

  return (
    <main className="pb-8">
      <ScreenHeader
        title="Sessions"
        subtitle={
          data && data.length > 0
            ? `${data.length} enregistrée(s)${pending ? ` · ${pending} à noter` : ""}`
            : undefined
        }
      />

      <SurfTabs />

      {offline.pending > 0 ? (
        <p className="flex items-center gap-2 px-5 pb-3 text-[13px] text-mute">
          <IconCloudOff className="h-4 w-4 shrink-0" />
          {offline.pending} notation(s) en attente d&apos;envoi
        </p>
      ) : null}

      {isPending ? (
        <p className="px-5 text-[14px] text-mute">Lecture de l&apos;historique…</p>
      ) : error ? (
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Historique indisponible. Réessaie quand le réseau revient.
        </p>
      ) : data && data.length > 0 ? (
        <ul className="mx-5 overflow-hidden rounded-card border border-line bg-card">
          {data.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </ul>
      ) : (
        <section className="px-5">
          <article className="rounded-card border border-line bg-card px-5 py-6">
            <h2 className="font-display text-[24px] font-semibold leading-none uppercase text-ink">
              Aucune session
            </h2>
            <p className="mt-3 text-[15px] leading-snug text-ink-2">
              La première s&apos;enregistre en sortant de l&apos;eau, depuis le
              raccourci iPhone. Il se met en place une fois, dans le profil.
            </p>
            <Link
              href="/profil/jetons"
              className="mt-4 flex min-h-touch items-center justify-center rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent"
            >
              Mettre en place le raccourci
            </Link>
          </article>
        </section>
      )}
    </main>
  );
}
