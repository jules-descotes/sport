"use client";

import { IconCamera } from "@/components/ui/Icons";
import { canEmbedWebcam } from "@/lib/webcam-hosts";

/**
 * La webcam d'un spot — iframe quand c'est possible, lien sortant sinon.
 *
 * Jamais de ré-hébergement du flux : droits et bande passante (`PROJET.md`
 * §10.4). Et jamais d'iframe vers un hôte absent de l'allowlist
 * (`lib/webcam-hosts.ts`), pour deux raisons qui vont dans le même sens :
 *
 * - la CSP l'interdirait, et le navigateur bloquerait **sans un mot** : on
 *   verrait un cadre blanc, pas une erreur ;
 * - la plupart des webcams de la côte refusent l'encadrement par en-tête
 *   (`X-Frame-Options`), et un cadre blanc ment sur l'existence de l'image.
 *
 * Un lien sortant honnête vaut mieux qu'un cadre qui ne chargera pas. L'URL
 * est de toute façon en `https:` : le back refuse le clair à la saisie.
 */
export function Webcam({ url, name }: { url: string | null; name: string }) {
  if (!url) {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-card border border-dashed border-line bg-soft text-mute">
        <IconCamera className="h-7 w-7" />
        <p className="text-[13px]">Pas de webcam pour ce spot</p>
      </div>
    );
  }

  if (canEmbedWebcam(url)) {
    return (
      <div className="overflow-hidden rounded-card border border-line bg-soft">
        <iframe
          src={url}
          title={`Webcam ${name}`}
          className="aspect-video w-full"
          loading="lazy"
          referrerPolicy="no-referrer"
          // Pas de `allow` : un iframe de webcam n'a rien à demander à
          // l'appareil. La Permissions-Policy le lui refuserait de toute façon.
          sandbox="allow-scripts allow-same-origin allow-presentation"
          allowFullScreen
        />
      </div>
    );
  }

  let host = url;
  try {
    host = new URL(url).hostname;
  } catch {
    // URL illisible : on affiche ce qu'on a, le lien reste cliquable.
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex min-h-touch items-center gap-3 rounded-card border border-line bg-card px-4 py-3"
    >
      <IconCamera className="h-5 w-5 shrink-0 text-mute" />
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-semibold text-ink">
          Voir la webcam
        </span>
        <span className="block truncate text-[12px] text-mute">
          {host} · s&apos;ouvre dans un onglet
        </span>
      </span>
    </a>
  );
}
