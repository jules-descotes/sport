/**
 * Icônes en trait, épaisseur 1,75 px, jamais d'emoji (cf. CLAUDE.md).
 * Dessinées sur une grille 24 : un seul jeu, une seule graisse.
 */
interface IconProps {
  className?: string;
}

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** Surf — une houle qui déferle. */
export function IconWave({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M2 16.5c2 0 2.5-2 4.5-2s2.5 2 4.5 2 2.5-2 4.5-2 2.5 2 4.5 2" />
      <path d="M4.5 11.5c1.6-3.6 4.6-5.5 8-5.5 2.6 0 4.6 1.1 5.8 2.6" />
      <path d="M18.3 8.6 15 9.4" />
    </svg>
  );
}

/** Jour — le soleil sur l'horizon : la journée en cours. */
export function IconDay({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12.5" r="3.6" />
      <path d="M12 4v2M12 19v2M4.9 5.4l1.4 1.4M17.7 18.2l1.4 1.4M3 12.5h2M19 12.5h2M4.9 19.6l1.4-1.4M17.7 6.8l1.4-1.4" />
    </svg>
  );
}

/** Corps — silhouette : objectifs, formules, composition. */
export function IconBody({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="5.2" r="2.4" />
      <path d="M12 7.6v7M12 14.6 8.5 20M12 14.6 15.5 20M7.5 10h9" />
    </svg>
  );
}

/** Recherche. */
export function IconSearch({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="11" cy="11" r="6" />
      <path d="m15.5 15.5 4 4" />
    </svg>
  );
}

/** Training — haltère. */
export function IconDumbbell({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 9v6M7 7.5v9M17 7.5v9M20 9v6" />
      <path d="M7 12h10" />
    </svg>
  );
}

/** Nutrition — assiette et couvert. */
export function IconPlate({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="11" cy="12" r="7" />
      <circle cx="11" cy="12" r="3.2" />
      <path d="M20 4v16" />
    </svg>
  );
}

/** Stats — courbe de progression. */
export function IconChart({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 4v15.5h16" />
      <path d="M7.5 15l3.5-4.5 3 2.5L20 7" />
    </svg>
  );
}

/** Déconnexion. */
export function IconLogout({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M14 4h4.5a1.5 1.5 0 0 1 1.5 1.5v13a1.5 1.5 0 0 1-1.5 1.5H14" />
      <path d="M9 8.5 5 12l4 3.5" />
      <path d="M5 12h10" />
    </svg>
  );
}

/** Favori — l'étoile pleine signale un spot maison, donc ingéré en planifié. */
export function IconStar({
  className,
  filled = false,
}: IconProps & { filled?: boolean }) {
  return (
    <svg {...base} className={className} fill={filled ? "currentColor" : "none"}>
      <path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.6-4.8 2.6.9-5.4L4.2 9.7l5.4-.8z" />
    </svg>
  );
}

/** Masquer un spot — œil barré. */
export function IconEyeOff({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 12s3.2-5.5 8-5.5c1.3 0 2.5.4 3.5 1" />
      <path d="M19.2 9.2c.5.6.8 1.2.8 1.2v.1s-3.2 5.5-8 5.5c-1 0-2-.2-2.8-.6" />
      <circle cx="12" cy="11.5" r="2.4" />
      <path d="m4.5 19.5 15-15" />
    </svg>
  );
}

/** Carte — épingle de position. */
export function IconPin({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 21s6.5-6.1 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 14.9 12 21 12 21Z" />
      <circle cx="12" cy="10.5" r="2.4" />
    </svg>
  );
}

/** Comparateur — grille heures × spots. */
export function IconGrid({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 10h16M4 15h16M10 4v16" />
    </svg>
  );
}

/** Webcam. */
export function IconCamera({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 8.5h10.5a1.5 1.5 0 0 1 1.5 1.5v5a1.5 1.5 0 0 1-1.5 1.5H4z" />
      <path d="m16 12.5 4-2.5v7l-4-2.5z" />
    </svg>
  );
}

/** Profil. */
export function IconUser({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" />
    </svg>
  );
}

/** Retour. */
export function IconBack({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m14 5-7 7 7 7" />
    </svg>
  );
}

/** Localisation en cours / recentrer la carte. */
export function IconCrosshair({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="6.5" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
    </svg>
  );
}

/** Plus — ajouter un spot. */
export function IconPlus({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
