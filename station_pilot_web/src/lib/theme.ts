import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "station-pilot-theme";
const listeners = new Set<() => void>();

function systemPreference(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedPreference(): Theme | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

let current: Theme = storedPreference() ?? systemPreference();

function paint(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? "#0b110f" : "#f5f7f6");
}

paint(current);

/** Suit le réglage système tant que l'utilisateur n'a pas choisi explicitement. */
window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
  if (storedPreference()) return;
  current = event.matches ? "dark" : "light";
  paint(current);
  listeners.forEach((listener) => listener());
});

export function setTheme(theme: Theme) {
  current = theme;
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* stockage indisponible : le thème reste valable pour la session */
  }
  paint(theme);
  listeners.forEach((listener) => listener());
}

export function toggleTheme() {
  setTheme(current === "dark" ? "light" : "dark");
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => "light" as Theme,
  );
}

/**
 * Couleurs des graphiques. Les deux modes sont choisis puis validés
 * (bande de clarté, plancher de chroma, séparation daltonisme, contraste)
 * contre la surface réelle des cartes : #ffffff en clair, #141b18 en sombre.
 */
export interface ChartTheme {
  sales: string;
  expenses: string;
  net: string;
  /** Séries de comparaison : même teinte, tracé pointillé + libellé « préc. ». */
  salesCompare: string;
  expensesCompare: string;
  netCompare: string;
  positive: string;
  negative: string;
  grid: string;
  axis: string;
  tick: string;
  tooltipBackground: string;
  tooltipBorder: string;
  tooltipText: string;
  /** Fond réel de la carte : sert d'écart de 2 px entre marques adjacentes. */
  surface: string;
  areaOpacity: number;
  /** Ordre fixe, jamais recyclé au-delà de 8 séries. */
  categorical: string[];
}

const lightChart: ChartTheme = {
  sales: "#1baf7a",
  expenses: "#eb6834",
  net: "#2a78d6",
  salesCompare: "#8ed7bd",
  expensesCompare: "#f5b49a",
  netCompare: "#95bceb",
  positive: "#0ca30c",
  negative: "#d03b3b",
  grid: "#e6ece9",
  axis: "#c6d3cd",
  tick: "#65766d",
  tooltipBackground: "#072d22",
  tooltipBorder: "rgba(255,255,255,.12)",
  tooltipText: "#ffffff",
  surface: "#ffffff",
  areaOpacity: 0.3,
  categorical: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
};

const darkChart: ChartTheme = {
  sales: "#199e70",
  expenses: "#d95926",
  net: "#3987e5",
  salesCompare: "#0f5b41",
  expensesCompare: "#7d3416",
  netCompare: "#204d83",
  positive: "#0ca30c",
  negative: "#d03b3b",
  grid: "#22302b",
  axis: "#35473f",
  tick: "#94a8a0",
  tooltipBackground: "#0b1613",
  tooltipBorder: "rgba(255,255,255,.16)",
  tooltipText: "#eaf3ef",
  surface: "#141b18",
  areaOpacity: 0.26,
  categorical: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};

export function useChartTheme(): ChartTheme {
  return useTheme() === "dark" ? darkChart : lightChart;
}
