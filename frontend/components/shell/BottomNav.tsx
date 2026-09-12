"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { IconBody, IconDay, IconWave } from "@/components/ui/Icons";

/**
 * Trois destinations, et trois seulement (décidé le 12/09 au soir,
 * cf. PROJET.md §1) :
 *
 * - **Jour** — la journée en cours, tous domaines mêlés ;
 * - **Mer** — l'explorateur : la prévision de n'importe quel spot du catalogue ;
 * - **Corps** — objectifs, formules, composition.
 *
 * Elles remplacent les quatre onglets Surf / Training / Nutrition / Stats,
 * dont deux affichaient « arrive au lot 4 ». Le training et la nutrition
 * entrent désormais par la porte « Corps », qui existe dès le premier jour.
 */
const TABS = [
  { href: "/", label: "Jour", Icon: IconDay },
  { href: "/mer", label: "Mer", Icon: IconWave },
  { href: "/corps", label: "Corps", Icon: IconBody },
] as const;

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Navigation principale"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="mx-auto flex max-w-2xl">
        {TABS.map(({ href, label, Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-touch flex-col items-center justify-center gap-1 px-2 py-2 text-[12px] font-medium transition-colors ${
                  active ? "text-accent" : "text-mute"
                }`}
              >
                <Icon className="h-6 w-6" />
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
