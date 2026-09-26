import { Moon, Sun } from "lucide-react";
import { toggleTheme, useTheme } from "../lib/theme";

interface ThemeToggleProps {
  /** `rail` : version compacte pour la barre latérale sombre. */
  variant?: "bar" | "rail";
}

export function ThemeToggle({ variant = "bar" }: ThemeToggleProps) {
  const theme = useTheme();
  const nextLabel = theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre";

  return (
    <button
      type="button"
      className={`theme-toggle theme-toggle--${variant}`}
      onClick={toggleTheme}
      title={nextLabel}
      aria-label={nextLabel}
    >
      <span className="theme-toggle__track" aria-hidden="true">
        <span className="theme-toggle__thumb">{theme === "dark" ? <Moon size={14} /> : <Sun size={14} />}</span>
      </span>
      <span className="theme-toggle__text">{theme === "dark" ? "Sombre" : "Clair"}</span>
    </button>
  );
}
