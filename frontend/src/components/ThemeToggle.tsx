"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export const THEME_STORAGE_KEY = "swapdesk-theme";

type Theme = "dark" | "light";

export function ThemeToggle({ expanded = false }: { expanded?: boolean }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    // Sync React state with the class applied by the pre-hydration script.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(
      document.documentElement.classList.contains("light") ? "light" : "dark",
    );
  }, []);

  const toggle = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.classList.toggle("light", next === "light");
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* storage unavailable (private mode) — theme still applies for the session */
    }
  };

  const isLight = theme === "light";
  const label = isLight ? "Switch to dark mode" : "Switch to light mode";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      aria-pressed={isLight}
      className={`grid h-10 place-items-center rounded-xl border border-hairline text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground ${expanded ? "w-full grid-flow-col gap-3 px-3" : "w-10"}`}
    >
      <span className="flex items-center gap-2">
        {isLight ? <Moon className="h-[18px] w-[18px] shrink-0" /> : <Sun className="h-[18px] w-[18px] shrink-0" />}
        {expanded && <span className="truncate text-[11px]">{isLight ? "Dark mode" : "Light mode"}</span>}
        {!expanded && <span className="sr-only">{label}</span>}
      </span>
    </button>
  );
}
