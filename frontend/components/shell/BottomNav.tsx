"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  IconDay,
  IconDumbbell,
  IconPlate,
  IconUser,
  IconWave,
} from "@/components/ui/Icons";
import { TABS, type TabIcon, activeTab } from "@/lib/navigation";

/**
 * Cinq entrées : **Jour / Surf / Training / Nutrition / Profil**.
 *
 * La liste elle-même vit dans `lib/navigation.ts` — voir son commentaire pour
 * le pourquoi de chaque entrée. Ici, rien que le rendu.
 *
 * À 390 px, cinq cibles de 78 px de large : au-dessus des 44 px exigés, et le
 * libellé le plus long (« Nutrition ») tient à 12 px sans césure.
 */
const ICONS: Record<TabIcon, (props: { className?: string }) => React.ReactNode> =
  {
    day: IconDay,
    wave: IconWave,
    dumbbell: IconDumbbell,
    plate: IconPlate,
    user: IconUser,
  };

export function BottomNav() {
  const pathname = usePathname();
  const current = activeTab(pathname);

  return (
    <nav
      aria-label="Navigation principale"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="mx-auto flex max-w-2xl">
        {TABS.map(({ href, label, icon }) => {
          const Icon = ICONS[icon];
          const active = current === href;
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-touch flex-col items-center justify-center gap-1 px-1 py-2 text-[12px] font-medium transition-colors ${
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
