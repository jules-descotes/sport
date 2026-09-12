interface ScreenHeaderProps {
  title: string;
  subtitle?: string;
}

export function ScreenHeader({ title, subtitle }: ScreenHeaderProps) {
  return (
    <header className="px-5 pb-4 pt-6">
      <h1 className="text-[32px] leading-none font-semibold uppercase tracking-wide text-ink">
        {title}
      </h1>
      {subtitle ? (
        <p className="mt-2 text-[14px] text-ink-2">{subtitle}</p>
      ) : null}
    </header>
  );
}
