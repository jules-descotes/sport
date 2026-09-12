import { create } from "zustand";

import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  setUser: (user: User | null) => void;
}

/** Miroir en mémoire de la session. La vérité reste le cookie httpOnly :
 *  ce store n'est qu'un cache pour éviter de redemander /auth/me à chaque écran. */
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
}));
