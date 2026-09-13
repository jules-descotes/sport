/**
 * Les hôtes de webcam autorisés en iframe — **et la source unique** de la
 * directive `frame-src` de la Content-Security-Policy.
 *
 * Ce fichier est importé par `next.config.ts` (qui fabrique l'en-tête) et par
 * le composant de webcam (qui décide iframe ou lien sortant). Deux listes
 * auraient divergé au premier ajout, et la panne aurait été silencieuse : un
 * cadre blanc, sans message, parce que le navigateur bloque sans rien dire.
 *
 * Tout est en `https:`, sans exception. Une webcam servie en clair sur une
 * page en HTTPS est bloquée comme contenu mixte par tous les navigateurs
 * depuis des années : la question n'est pas de savoir si on l'accepte, c'est
 * qu'elle ne s'affichera pas.
 *
 * Un hôte absent de cette liste n'est pas refusé : il est affiché en **lien
 * sortant** plutôt qu'en iframe. C'est le bon comportement par défaut, parce
 * que la plupart des webcams de la côte interdisent l'encadrement par en-tête
 * (`X-Frame-Options`) et qu'un iframe vide ment sur l'existence de l'image.
 */

/**
 * Hôtes et sous-domaines admis **par défaut**. Un point en tête vaut « ce
 * domaine et tous ses sous-domaines » ; sans point, l'hôte doit correspondre
 * exactement.
 *
 * Cette liste est **pilotée par `WEBCAM_FRAME_HOSTS`** (décidé le 13/09,
 * retours n° 4) : une variable d'environnement, séparée par des virgules, qui
 * **s'ajoute** à ces défauts. Ajouter l'hôte d'un office de tourisme ne doit
 * pas demander un déploiement — c'est le genre de chose qu'on découvre un
 * dimanche matin, l'inspecteur du navigateur ouvert sur la page d'une webcam
 * qu'on voudrait voir tout de suite.
 *
 * Elle ajoute et ne remplace pas : une variable mal écrite retirerait sinon
 * toutes les webcams d'un coup, et le symptôme serait des cadres vides sans
 * message.
 */
const DEFAULT_WEBCAM_FRAME_HOSTS: readonly string[] = [
  // Windy — la seule source de catalogue prévue (PROJET.md §6).
  ".windy.com",
  // YouTube et Vimeo : la majorité des webcams de plage passent par là.
  ".youtube.com",
  ".youtube-nocookie.com",
  "www.youtube-nocookie.com",
  ".vimeo.com",
  "player.vimeo.com",
  // Diffuseurs de webcams côtières couramment encadrables.
  ".skylinewebcams.com",
  ".viewsurf.com",
  ".surfline.com",
  ".ipcamlive.com",
  ".livecam.com",
  // Les hôtes relevés le 13/09 à l'inspecteur, sur les pages des offices de
  // tourisme de la côte. Ce sont des **URL d'iframe**, pas des pages : les
  // pages chargent leur cadre dynamiquement, et encadrer la page ne montre
  // rien.
  "loujo.fr",
  ".loujo.fr",
  ".skaping.com",
  ".vision-environnement.com",
] as const;

function fromEnvironment(): string[] {
  // `NEXT_PUBLIC_` : la liste est lue côté client par le composant de webcam,
  // et côté build par `next.config.ts` pour fabriquer la CSP. Une variable
  // serveur ne serait visible que d'un des deux, et le cadre serait bloqué
  // par une politique que le composant croirait permissive.
  const raw = process.env.NEXT_PUBLIC_WEBCAM_FRAME_HOSTS ?? "";
  return raw
    .split(",")
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
}

export const WEBCAM_FRAME_HOSTS: readonly string[] = [
  ...new Set([...DEFAULT_WEBCAM_FRAME_HOSTS, ...fromEnvironment()]),
];

/** Les sources `frame-src` de la CSP : `https://*.windy.com`, etc. */
export function frameSrcSources(): string[] {
  return WEBCAM_FRAME_HOSTS.map((host) =>
    host.startsWith(".") ? `https://*${host}` : `https://${host}`,
  );
}

/**
 * Cette URL peut-elle être encadrée ?
 *
 * Faux pour tout ce qui n'est pas une URL `https:` d'un hôte de la liste —
 * y compris une URL invalide, qui ne doit pas faire tomber le rendu.
 */
export function canEmbedWebcam(url: string | null | undefined): boolean {
  if (!url) return false;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:") return false;

  const host = parsed.hostname.toLowerCase();
  return WEBCAM_FRAME_HOSTS.some((allowed) =>
    allowed.startsWith(".")
      ? host === allowed.slice(1) || host.endsWith(allowed)
      : host === allowed,
  );
}
