"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Les trois portes de Surf : la prévision, l'historique, le matos.
 *
 * Surf a absorbé les sessions et le matos le 13/09 — tout ce qui touche à
 * l'eau entre par la même porte, et le profil redevient ce qu'il doit être :
 * des réglages. Ce sélecteur est un sous-niveau, pas une quatrième entrée de
 * la barre basse : la règle des cinq destinations tient.
 */
const LINKS = [
  { href: "/surf", label: "Prévision" },
  { href: "/surf/sessions", label: "Sessions" },
  { href: "/surf/matos", label: "Matos" },
] as const;

export function SurfTabs() {
  const pathname = usePathname();

  return (
    <nav aria-label="Sections de Surf" className="px-5 pb-3">
      <ul className="flex gap-2">
        {LINKS.map(({ href, label }) => {
          const active =
            href === "/surf" ? pathname === "/surf" : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-touch items-center rounded-pill border px-4 text-[14px] font-semibold ${
                  active
                    ? "border-ink bg-ink text-bg"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
