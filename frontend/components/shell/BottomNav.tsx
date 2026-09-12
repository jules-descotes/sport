"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  IconChart,
  IconDumbbell,
  IconPlate,
  IconWave,
} from "@/components/ui/Icons";

const TABS = [
  { href: "/", label: "Surf", Icon: IconWave },
  { href: "/training", label: "Training", Icon: IconDumbbell },
  { href: "/nutrition", label: "Nutrition", Icon: IconPlate },
  { href: "/stats", label: "Stats", Icon: IconChart },
] as const;

/**
 * Barre basse fixe, zone du pouce. Pas de menu hamburger sur les parcours
 * quotidiens : quatre onglets, toujours les mêmes, toujours au même endroit.
 */
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
