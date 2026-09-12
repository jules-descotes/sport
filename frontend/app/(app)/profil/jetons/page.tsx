"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { IconBack, IconCheck, IconKey, IconPlus } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { shortDate } from "@/lib/format";

/**
 * **Jetons** — ce qui fait marcher le raccourci iPhone.
 *
 * Le raccourci iOS « Obtenir le contenu de l'URL » n'a pas de magasin de
 * cookies : le cookie de session ne lui parviendrait pas. Il lui faut un jeton
 * Bearer, et comme ce jeton vit un an sur un téléphone qui peut se perdre, il
 * doit se couper d'ici — sans déconnecter le navigateur.
 *
 * La valeur ne s'affiche **qu'une fois**, à la création : elle n'est pas
 * stockée côté serveur, qui ne garde que de quoi la révoquer. C'est dit à
 * l'écran, parce que c'est le seul moment où on peut la copier.
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div>
      <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {label}
      </p>
      <div className="flex items-stretch gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-button border border-line bg-soft px-3 py-2.5 text-[13px] leading-relaxed text-ink">
          {value}
        </code>
        <button
          type="button"
          onClick={() => {
            // `clipboard` peut manquer (contexte non sécurisé) : la valeur
            // reste sélectionnable à la main, et le bouton ne ment pas.
            navigator.clipboard
              ?.writeText(value)
              .then(() => setCopied(true))
              .catch(() => setCopied(false));
          }}
          aria-label={`Copier ${label}`}
          className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button border border-line bg-card text-ink-2"
        >
          {copied ? (
            <IconCheck className="h-5 w-5 text-accent" />
          ) : (
            <IconKey className="h-5 w-5" />
          )}
        </button>
      </div>
    </div>
  );
}

export default function JetonsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [fresh, setFresh] = useState<string | null>(null);

  const { data, isPending } = useQuery({
    queryKey: ["tokens"],
    queryFn: api.tokens,
  });

  const create = useMutation({
    mutationFn: () => api.createToken("Raccourci iPhone"),
    onSuccess: (token) => {
      setFresh(token.token);
      queryClient.invalidateQueries({ queryKey: ["tokens"] });
    },
  });

  const revoke = useMutation({
    mutationFn: (id: number) => api.revokeToken(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tokens"] }),
  });

  const active = (data ?? []).filter((token) => token.revoked_at === null);

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
          Raccourci iPhone
        </h1>
        <p className="mt-2 text-[15px] leading-snug text-ink-2">
          Un jeton, un raccourci, et une session s&apos;enregistre en sortant de
          l&apos;eau sans ouvrir l&apos;app. La recette complète est dans{" "}
          <code className="text-[13px]">docs/RACCOURCI-IOS.md</code>.
        </p>
      </section>

      {fresh ? (
        <section className="px-5 pb-6">
          <article className="flex flex-col gap-4 rounded-card border border-accent bg-card px-4 py-4">
            <p className="text-[14px] font-semibold leading-snug text-ink">
              Copie le jeton maintenant : il ne sera plus jamais affiché.
            </p>
            <CopyRow label="Jeton" value={fresh} />
            <CopyRow label="URL à appeler" value={`${API_URL}/sessions/quick`} />
            <CopyRow label="En-tête" value={`Authorization: Bearer ${fresh}`} />
            <button
              type="button"
              onClick={() => setFresh(null)}
              className="min-h-touch rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent"
            >
              C&apos;est copié
            </button>
          </article>
        </section>
      ) : null}

      <section className="flex flex-col gap-3 px-5">
        {isPending ? (
          <p className="text-[14px] text-mute">Chargement…</p>
        ) : (data ?? []).length === 0 ? (
          <p className="rounded-card border border-dashed border-line bg-soft px-4 py-4 text-[14px] leading-snug text-ink-2">
            Aucun jeton. Sans lui, le raccourci ne peut pas s&apos;authentifier —
            le cookie de session ne sort pas du navigateur.
          </p>
        ) : (
          (data ?? []).map((token) => {
            const revoked = token.revoked_at !== null;
            return (
              <article
                key={token.id}
                className={`flex items-center gap-3 rounded-card border border-line bg-card px-4 py-3 ${
                  revoked ? "opacity-55" : ""
                }`}
              >
                <IconKey className="h-5 w-5 shrink-0 text-mute" />
                <div className="min-w-0 flex-1">
                  <p
                    className={`truncate text-[15px] font-semibold text-ink ${
                      revoked ? "line-through" : ""
                    }`}
                  >
                    {token.name}
                  </p>
                  <p className="tabular text-[12px] text-mute">
                    {revoked
                      ? `révoqué le ${shortDate(token.revoked_at as string)}`
                      : token.last_used_at
                        ? `dernier appel le ${shortDate(token.last_used_at)}`
                        : "jamais utilisé"}
                    {` · expire le ${shortDate(token.expires_at)}`}
                  </p>
                </div>
                {!revoked ? (
                  <button
                    type="button"
                    onClick={() => revoke.mutate(token.id)}
                    disabled={revoke.isPending}
                    className="min-h-touch shrink-0 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2 disabled:opacity-50"
                  >
                    Révoquer
                  </button>
                ) : null}
              </article>
            );
          })
        )}

        <button
          type="button"
          onClick={() => create.mutate()}
          disabled={create.isPending}
          className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2 disabled:opacity-50"
        >
          <IconPlus className="h-5 w-5" />
          {create.isPending ? "Création…" : "Créer un jeton"}
        </button>

        {active.length > 1 ? (
          <p className="text-[12px] leading-snug text-mute">
            Plusieurs jetons actifs : garde celui du téléphone et révoque les
            autres. Un jeton qui n&apos;a jamais servi n&apos;a aucune raison de
            rester valable un an.
          </p>
        ) : null}
      </section>
    </main>
  );
}
