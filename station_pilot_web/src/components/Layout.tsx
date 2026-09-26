import { BarChart3, CircleDollarSign, Database, Fuel, HandCoins, House, Menu, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { Page } from "../types";
import { ThemeToggle } from "./ThemeToggle";

const navItems: { id: Page; label: string; short: string; description: string; icon: typeof Fuel }[] = [
  { id: "overview", label: "Vue d’ensemble", short: "Accueil", description: "L’essentiel de la station, immédiatement", icon: House },
  { id: "entry", label: "Saisie journalière", short: "Saisie", description: "Enregistrer et clôturer la journée", icon: Fuel },
  { id: "dashboard", label: "Tableau de bord", short: "Dashboard", description: "Comprendre les performances en un regard", icon: BarChart3 },
  { id: "credits", label: "Suivi des crédits", short: "Crédits", description: "Piloter les soldes et remboursements clients", icon: HandCoins },
  { id: "history", label: "Historique & exports", short: "Historique", description: "Retrouver, contrôler et exporter les données", icon: Database },
];

interface LayoutProps {
  page: Page;
  onPageChange: (page: Page) => void;
  latestDate?: string;
  children: ReactNode;
}

export function Layout({ page, onPageChange, latestDate, children }: LayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.body.classList.add("nav-open");
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.classList.remove("nav-open");
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileOpen]);

  const navigate = (next: Page) => {
    onPageChange(next);
    setMobileOpen(false);
  };

  return (
    <div className="app-shell">
      <button
        type="button"
        className={`sidebar-scrim ${mobileOpen ? "visible" : ""}`}
        aria-label="Fermer le menu"
        tabIndex={mobileOpen ? 0 : -1}
        onClick={() => setMobileOpen(false)}
      />
      <aside id="app-sidebar" className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`} aria-label="Menu principal">
        <div className="brand">
          <div className="brand-mark"><Fuel size={25} /></div>
          <div>
            <strong>Station Pilot</strong>
            <span>Gestion USD / LL</span>
          </div>
          <button type="button" className="icon-button mobile-close" aria-label="Fermer le menu" onClick={() => setMobileOpen(false)}>
            <X size={20} />
          </button>
        </div>
        <span className="nav-section-label">Espace de travail</span>
        <nav className="side-nav" aria-label="Navigation principale">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={page === item.id ? "nav-item active" : "nav-item"}
                aria-current={page === item.id ? "page" : undefined}
                onClick={() => navigate(item.id)}
              >
                <Icon size={19} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-status" role="status">
          <div className="status-dot" />
          <div>
            <strong>Base locale active</strong>
            <span>SQLite + sauvegardes CSV</span>
          </div>
        </div>
        <ThemeToggle variant="rail" />
        <div className="sidebar-footer">
          <CircleDollarSign size={17} />
          Conversion au taux de chaque jour
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button
            type="button"
            className="icon-button menu-button"
            aria-label="Ouvrir le menu"
            aria-expanded={mobileOpen}
            aria-controls="app-sidebar"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={22} />
          </button>
          <div>
            <h1>{navItems.find((item) => item.id === page)?.label}</h1>
            <p>{navItems.find((item) => item.id === page)?.description}</p>
          </div>
          <div className="topbar-actions">
            <ThemeToggle />
            <div className="topbar-meta">
              <span>Dernière clôture</span>
              <strong>{latestDate || "Aucune donnée"}</strong>
            </div>
          </div>
        </header>
        <div className="content">{children}</div>
      </main>

      <nav className="bottom-nav" aria-label="Navigation mobile">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              aria-current={page === item.id ? "page" : undefined}
              onClick={() => navigate(item.id)}
            >
              <Icon size={19} aria-hidden="true" />
              <span>{item.short}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
