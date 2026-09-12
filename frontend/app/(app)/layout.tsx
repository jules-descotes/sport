"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { BottomNav } from "@/components/shell/BottomNav";
import { ApiError, api } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";

export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const setUser = useAuthStore((state) => state.setUser);

  // La vérité de la session est le cookie httpOnly : on ne peut pas la lire
  // côté client, on la demande au back. Le back Railway peut démarrer à froid,
  // d'où l'état de chargement explicite plutôt qu'un écran blanc.
  const { data, isPending, error } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: (failureCount, err) =>
      err instanceof ApiError && err.status === 401 ? false : failureCount < 2,
  });

  useEffect(() => {
    if (data) setUser(data);
  }, [data, setUser]);

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      router.replace("/login");
    }
  }, [error, router]);

  if (isPending) {
    return (
      <main className="flex min-h-dvh items-center justify-center px-5">
        <p className="text-[14px] text-mute">Chargement…</p>
      </main>
    );
  }

  if (error) {
    const offline = error instanceof ApiError && error.status === 0;
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-5 text-center">
        <p className="text-[16px] text-ink">
          {offline
            ? "Pas de réseau."
            : "Le serveur ne répond pas pour le moment."}
        </p>
        <p className="text-[14px] text-mute">
          Les données déjà enregistrées restent disponibles.
        </p>
      </main>
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col">
      {/* La barre basse est fixe : on réserve sa hauteur plus la zone sûre iOS. */}
      <div className="flex-1 pb-[calc(76px+env(safe-area-inset-bottom))]">
        {children}
      </div>
      <BottomNav />
    </div>
  );
}
