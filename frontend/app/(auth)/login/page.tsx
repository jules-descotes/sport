"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";

import { ApiError, api } from "@/lib/api";
import { loginSchema, type LoginValues } from "@/lib/schemas";
import { useAuthStore } from "@/lib/store/auth";

export default function LoginPage() {
  const router = useRouter();
  const setUser = useAuthStore((state) => state.setUser);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const login = useMutation({
    mutationFn: async (values: LoginValues) => {
      await api.login(values.email, values.password);
      return api.me();
    },
    onSuccess: (user) => {
      setUser(user);
      router.replace("/");
    },
  });

  const errorMessage =
    login.error instanceof ApiError
      ? login.error.status === 0
        ? "Pas de réseau. Réessaie quand la connexion revient."
        : login.error.message
      : login.error
        ? "Une erreur est survenue"
        : null;

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-5 py-10">
      <h1 className="text-[40px] leading-none font-bold uppercase tracking-wide text-ink">
        Sport
      </h1>
      <p className="mt-3 text-[14px] text-ink-2">
        Surf, training, nutrition. Un seul compte.
      </p>

      <form
        onSubmit={handleSubmit((values) => login.mutate(values))}
        className="mt-8 flex flex-col gap-5"
        noValidate
      >
        <div className="flex flex-col gap-2">
          <label
            htmlFor="email"
            className="text-[12px] font-semibold uppercase tracking-wide text-mute"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            className="min-h-touch rounded-button border border-line bg-card px-4 text-[16px] text-ink"
            {...register("email")}
          />
          {errors.email ? (
            <p className="text-[13px] text-accent">{errors.email.message}</p>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="password"
            className="text-[12px] font-semibold uppercase tracking-wide text-mute"
          >
            Mot de passe
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="min-h-touch rounded-button border border-line bg-card px-4 text-[16px] text-ink"
            {...register("password")}
          />
          {errors.password ? (
            <p className="text-[13px] text-accent">{errors.password.message}</p>
          ) : null}
        </div>

        {errorMessage ? (
          <p
            role="alert"
            className="rounded-cell border border-line bg-card px-4 py-3 text-[14px] text-ink"
          >
            {errorMessage}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={login.isPending}
          className="min-h-touch rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-60"
        >
          {login.isPending ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </main>
  );
}
