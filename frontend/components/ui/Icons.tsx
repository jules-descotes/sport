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
