import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  CircleAlert,
  Droplets,
  Fuel,
  Gauge,
  HandCoins,
  ReceiptText,
  ShieldCheck,
  Sparkles,
  WalletCards,
} from "lucide-react";
import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MetricCard } from "../components/MetricCard";
import { formatDate, formatLbp, formatNumber, formatUsd } from "../lib/format";
import { useChartTheme, type ChartTheme } from "../lib/theme";
import { localIsoDate, type CustomerSummary, type DailyRecord, type Page } from "../types";

interface OverviewPageProps {
  days: DailyRecord[];
  customers: CustomerSummary[];
  onNavigate: (page: Page) => void;
  onEditDay: (date: string) => void;
}

type HealthTone = "success" | "warning" | "critical" | "info";

interface HealthItem {
  title: string;
  detail: string;
  tone: HealthTone;
  icon: typeof Gauge;
}

const hasDebt = (customer: CustomerSummary) =>
  customer.balance.usd > 0.005 || customer.balance.lbp > 0.5;

function periodTotals(days: DailyRecord[]) {
  return days.reduce(
    (total, day) => ({
      sales: total.sales + day.totals.salesUsdEquivalent,
      net: total.net + day.totals.netUsdEquivalent,
      liters: total.liters + day.fuelVolumeSoldL,
    }),
    { sales: 0, net: 0, liters: 0 },
  );
}

function comparisonLabel(current: number, previous: number): string {
  if (!previous) return current ? "Première période de référence" : "Aucune activité enregistrée";
  const variation = ((current - previous) / Math.abs(previous)) * 100;
  return `${variation >= 0 ? "+" : ""}${formatNumber(variation, 1)} % vs période précédente`;
}

function shortDate(isoDate: string): string {
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" })
    .format(new Date(`${isoDate}T12:00:00`))
    .replace(".", "");
}

function OverviewTooltip({ active, payload, label, colors }: any) {
  if (!active || !payload?.length) return null;
  const theme = colors as ChartTheme;
  return (
    <div
      className="chart-tooltip overview-tooltip"
      style={{ background: theme.tooltipBackground, color: theme.tooltipText, borderColor: theme.tooltipBorder }}
    >
      <strong>{label}</strong>
      {payload.map((item: any) => (
        <span className="tooltip-row" key={item.dataKey}>
          <i style={{ background: item.color }} />
          <span>{item.name}</span>
          <b>{formatUsd(Number(item.value ?? 0))}</b>
        </span>
      ))}
    </div>
  );
}

export function OverviewPage({ days, customers, onNavigate, onEditDay }: OverviewPageProps) {
  const chart = useChartTheme();
  const sortedDays = useMemo(
    () => [...days].sort((a, b) => a.recordDate.localeCompare(b.recordDate)),
    [days],
  );
  const latest = sortedDays.at(-1);
  const recentDays = sortedDays.slice(-7);
  const previousDays = sortedDays.slice(-14, -7);
  const recent = periodTotals(recentDays);
  const previous = periodTotals(previousDays);
  const today = localIsoDate();
  const closedToday = latest?.recordDate === today;
  const latestRate = latest?.exchangeRate || 89_500;

  const dueCustomers = useMemo(
    () => customers
      .filter(hasDebt)
      .sort((a, b) => (
        Math.max(b.balance.usd, 0) + Math.max(b.balance.lbp, 0) / latestRate
        - Math.max(a.balance.usd, 0) - Math.max(a.balance.lbp, 0) / latestRate
      )),
    [customers, latestRate],
  );
  const outstanding = useMemo(
    () => dueCustomers.reduce((total, customer) => ({
      usd: total.usd + Math.max(customer.balance.usd, 0),
      lbp: total.lbp + Math.max(customer.balance.lbp, 0),
    }), { usd: 0, lbp: 0 }),
    [dueCustomers],
  );
  const outstandingEquivalent = outstanding.usd + outstanding.lbp / latestRate;

  const tankPercentage = latest && latest.tankCapacityL > 0
    ? Math.min(Math.max((latest.actualStockEndL / latest.tankCapacityL) * 100, 0), 100)
    : 0;
  const tankTone = !latest || latest.tankCapacityL <= 0
    ? "empty"
    : tankPercentage < 15 ? "critical" : tankPercentage < 30 ? "warning" : "healthy";

  const trendData = sortedDays.slice(-14).map((day) => ({
    label: shortDate(day.recordDate),
    ventes: day.totals.salesUsdEquivalent,
    resultat: day.totals.netUsdEquivalent,
  }));

  const healthItems: HealthItem[] = [];
  if (!latest) {
    healthItems.push({
      title: "Première clôture attendue",
      detail: "Commencez par saisir une journée pour activer les contrôles opérationnels.",
      tone: "info",
      icon: Sparkles,
    });
  } else {
    if (latest.tankCapacityL <= 0) {
      healthItems.push({ title: "Capacité du réservoir à renseigner", detail: "Le niveau de stock ne peut pas encore être évalué.", tone: "info", icon: Gauge });
    } else if (tankPercentage < 20) {
      healthItems.push({ title: "Niveau de carburant faible", detail: `${formatNumber(tankPercentage, 0)} % du réservoir disponible.`, tone: tankPercentage < 10 ? "critical" : "warning", icon: Fuel });
    } else {
      healthItems.push({ title: "Niveau de carburant maîtrisé", detail: `${formatNumber(latest.actualStockEndL)} L disponibles à la dernière clôture.`, tone: "success", icon: Fuel });
    }

    const stockThreshold = Math.max(5, latest.tankCapacityL * 0.005);
    const stockVariance = Math.abs(latest.totals.stockVarianceL);
    healthItems.push(stockVariance > stockThreshold
      ? { title: "Écart de stock à vérifier", detail: `${formatNumber(latest.totals.stockVarianceL, 1)} L entre le réel et le théorique.`, tone: "warning", icon: AlertTriangle }
      : { title: "Stock rapproché", detail: `Écart limité à ${formatNumber(latest.totals.stockVarianceL, 1)} L.`, tone: "success", icon: ShieldCheck });

    const cashVarianceEquivalent = Math.abs(latest.totals.cashVariance.usd)
      + Math.abs(latest.totals.cashVariance.lbp) / latest.exchangeRate;
    healthItems.push(cashVarianceEquivalent > 1
      ? { title: "Écart de caisse à contrôler", detail: `${formatUsd(latest.totals.cashVariance.usd)} · ${formatLbp(latest.totals.cashVariance.lbp)}`, tone: cashVarianceEquivalent > 50 ? "critical" : "warning", icon: CircleAlert }
      : { title: "Caisses rapprochées", detail: "Aucun écart significatif à la dernière clôture.", tone: "success", icon: CheckCircle2 });
  }

  healthItems.push(dueCustomers.length
    ? { title: `${dueCustomers.length} compte${dueCustomers.length > 1 ? "s" : ""} à recouvrer`, detail: `${formatUsd(outstanding.usd)} · ${formatLbp(outstanding.lbp)} à recevoir.`, tone: "warning", icon: HandCoins }
    : { title: "Aucun crédit en attente", detail: "Tous les comptes clients sont à jour.", tone: "success", icon: HandCoins });
  const issueCount = healthItems.filter((item) => item.tone === "critical" || item.tone === "warning").length;

  return (
    <div className="page-stack overview-page">
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <span className="hero-kicker"><Sparkles size={15} /> Centre de pilotage</span>
          <h2>Votre station, claire en un regard.</h2>
          <p>Suivez l’activité, repérez les écarts et accédez aux actions essentielles sans chercher dans les tableaux.</p>
          <div className="hero-actions">
            <button className="button hero-primary" onClick={() => closedToday && latest ? onEditDay(latest.recordDate) : onNavigate("entry")}>
              <ReceiptText size={18} /> {closedToday ? "Mettre à jour aujourd’hui" : "Clôturer une journée"}
            </button>
            <button className="button hero-secondary" onClick={() => onNavigate("dashboard")}>
              Voir les analyses <ArrowRight size={17} />
            </button>
          </div>
        </div>

        <div className="overview-live-card">
          <div className="live-card-heading">
            <span className={`live-status ${closedToday ? "current" : "waiting"}`}><i /> {closedToday ? "À jour" : "Dernière clôture"}</span>
            <strong>{latest ? formatDate(latest.recordDate) : "Aucune journée"}</strong>
          </div>
          <div className="live-card-values">
            <div><span>Ventes</span><strong>{latest ? formatUsd(latest.totals.salesUsdEquivalent) : "—"}</strong></div>
            <div><span>Résultat</span><strong className={latest && latest.totals.netUsdEquivalent < 0 ? "negative" : ""}>{latest ? formatUsd(latest.totals.netUsdEquivalent) : "—"}</strong></div>
            <div><span>Volume</span><strong>{latest ? `${formatNumber(latest.fuelVolumeSoldL)} L` : "—"}</strong></div>
          </div>
          <small>Montants consolidés en équivalent USD au taux de la journée.</small>
        </div>
      </section>

      <section className="quick-actions" aria-labelledby="quick-actions-title">
        <div className="section-title-line">
          <div><span className="eyebrow">ACCÈS DIRECTS</span><h3 id="quick-actions-title">Que souhaitez-vous faire ?</h3></div>
        </div>
        <div className="quick-action-grid">
          <button className="quick-action-card" onClick={() => onNavigate("entry")}>
            <span className="quick-action-icon green"><ReceiptText size={21} /></span>
            <span><strong>Saisir une journée</strong><small>Stocks, ventes, dépenses et caisses</small></span>
            <ArrowRight size={18} />
          </button>
          <button className="quick-action-card" onClick={() => onNavigate("dashboard")}>
            <span className="quick-action-icon blue"><BarChart3 size={21} /></span>
            <span><strong>Analyser l’activité</strong><small>Performances par jour, semaine ou mois</small></span>
            <ArrowRight size={18} />
          </button>
          <button className="quick-action-card" onClick={() => onNavigate("credits")}>
            <span className="quick-action-icon amber"><WalletCards size={21} /></span>
            <span><strong>Gérer les crédits</strong><small>Soldes clients et remboursements</small></span>
            <ArrowRight size={18} />
          </button>
        </div>
      </section>

      <section aria-labelledby="recent-period-title">
        <div className="section-title-line">
          <div><span className="eyebrow">PÉRIODE RÉCENTE</span><h3 id="recent-period-title">Les 7 dernières clôtures</h3></div>
          <span className="section-caption">{recentDays.length ? `${formatDate(recentDays[0].recordDate)} — ${formatDate(recentDays.at(-1)!.recordDate)}` : "En attente de données"}</span>
        </div>
        <div className="metrics-grid four overview-metrics">
          <MetricCard label="Ventes consolidées" value={recentDays.length ? formatUsd(recent.sales) : "—"} detail={comparisonLabel(recent.sales, previous.sales)} tone="green" />
          <MetricCard label="Résultat opérationnel" value={recentDays.length ? formatUsd(recent.net) : "—"} detail={`${recent.sales ? formatNumber((recent.net / recent.sales) * 100, 1) : "0,0"} % des ventes`} tone={recent.net >= 0 ? "green" : "red"} />
          <MetricCard label="Carburant vendu" value={recentDays.length ? `${formatNumber(recent.liters)} L` : "—"} detail={comparisonLabel(recent.liters, previous.liters)} tone="blue" />
          <MetricCard label="Crédits à recevoir" value={customers.length ? formatUsd(outstandingEquivalent) : "—"} detail={`${formatUsd(outstanding.usd)} + ${formatLbp(outstanding.lbp)}`} tone={dueCustomers.length ? "amber" : "green"} />
        </div>
      </section>

      <div className="overview-insight-grid">
        <section className="chart-card overview-trend-card">
          <div className="chart-heading overview-chart-heading">
            <div><span className="eyebrow">TENDANCE</span><h3>Ventes & résultat</h3><p>Les 14 dernières clôtures, en équivalent USD.</p></div>
            <div className="mini-legend" aria-label="Légende">
              <span><i style={{ background: chart.sales }} /> Ventes</span>
              <span><i style={{ background: chart.expenses }} /> Résultat</span>
            </div>
          </div>
          {trendData.length ? (
            <div className="chart-container overview-chart" role="img" aria-label="Graphique des ventes et du résultat sur les dernières clôtures">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={trendData} margin={{ top: 10, right: 5, bottom: 0, left: -20 }}>
                  <defs>
                    <linearGradient id="overviewSalesFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chart.sales} stopOpacity={chart.areaOpacity} />
                      <stop offset="100%" stopColor={chart.sales} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={chart.grid} />
                  <XAxis dataKey="label" axisLine={false} tickLine={false} minTickGap={24} tick={{ fill: chart.tick, fontSize: 11 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: chart.tick, fontSize: 11 }} tickFormatter={(value) => `$${formatNumber(Number(value))}`} />
                  <Tooltip content={<OverviewTooltip colors={chart} />} />
                  <Area type="monotone" dataKey="ventes" name="Ventes" stroke={chart.sales} strokeWidth={2} fill="url(#overviewSalesFill)" />
                  <Line type="monotone" dataKey="resultat" name="Résultat" stroke={chart.expenses} strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="overview-chart-empty"><BarChart3 size={30} /><span>La tendance apparaîtra après la première clôture.</span></div>
          )}
        </section>

        <section className="reservoir-card">
          <div className="reservoir-heading"><div><span className="eyebrow">RÉSERVOIR</span><h3>Niveau disponible</h3></div><Droplets size={21} /></div>
          <div className="reservoir-content">
            <div
              className={`reservoir-gauge ${tankTone}`}
              role="progressbar"
              aria-label="Niveau du réservoir"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(tankPercentage)}
            >
              <div className="reservoir-grid-lines" />
              <div className="reservoir-fill" style={{ height: `${tankPercentage}%` }}><span /></div>
              <div className="reservoir-reading"><strong>{latest?.tankCapacityL ? `${formatNumber(tankPercentage)} %` : "—"}</strong><span>disponible</span></div>
            </div>
            <div className="reservoir-stats">
              <div><span>Stock réel</span><strong>{latest ? `${formatNumber(latest.actualStockEndL)} L` : "—"}</strong></div>
              <div><span>Capacité</span><strong>{latest?.tankCapacityL ? `${formatNumber(latest.tankCapacityL)} L` : "—"}</strong></div>
              <div><span>Écart théorique</span><strong className={latest && Math.abs(latest.totals.stockVarianceL) > 5 ? "negative-text" : ""}>{latest ? `${formatNumber(latest.totals.stockVarianceL, 1)} L` : "—"}</strong></div>
            </div>
          </div>
        </section>
      </div>

      <div className="overview-bottom-grid">
        <section className="health-card">
          <div className="section-title-line">
            <div><span className="eyebrow">VIGILANCE</span><h3>État opérationnel</h3></div>
            <span className={`health-count ${issueCount ? "has-issues" : "all-clear"}`}>{issueCount ? `${issueCount} point${issueCount > 1 ? "s" : ""} à suivre` : "Tout est en ordre"}</span>
          </div>
          <div className="health-list">
            {healthItems.map((item) => {
              const Icon = item.icon;
              return (
                <div className={`health-item ${item.tone}`} key={item.title}>
                  <span className="health-icon"><Icon size={18} /></span>
                  <span><strong>{item.title}</strong><small>{item.detail}</small></span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="credit-preview-card">
          <div className="section-title-line">
            <div><span className="eyebrow">CRÉDITS CLIENTS</span><h3>À recouvrer</h3></div>
            <button className="text-button" onClick={() => onNavigate("credits")}>Tout voir <ArrowRight size={15} /></button>
          </div>
          {dueCustomers.length ? (
            <div className="debt-preview-list">
              {dueCustomers.slice(0, 4).map((customer) => (
                <button key={customer.id} onClick={() => onNavigate("credits")}>
                  <span className="debt-avatar">{customer.name.trim().slice(0, 1).toLocaleUpperCase("fr")}</span>
                  <span><strong>{customer.name}</strong><small>{customer.lastActivityDate ? `Dernière opération ${formatDate(customer.lastActivityDate)}` : "Compte actif"}</small></span>
                  <span className="debt-values"><strong>{formatUsd(Math.max(customer.balance.usd, 0))}</strong><small>{formatLbp(Math.max(customer.balance.lbp, 0))}</small></span>
                </button>
              ))}
            </div>
          ) : (
            <div className="credit-preview-empty"><CheckCircle2 size={29} /><strong>Comptes à jour</strong><span>Aucun montant n’est actuellement à recouvrer.</span></div>
          )}
        </section>
      </div>
    </div>
  );
}
