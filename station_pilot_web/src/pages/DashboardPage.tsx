import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  Droplets,
  Gauge,
  GitCompareArrows,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MetricCard, type MetricDelta } from "../components/MetricCard";
import { toUsd } from "../lib/calculations";
import { formatDate, formatLbp, formatNumber, formatUsd, isoWeek, monthNames } from "../lib/format";
import { useChartTheme, type ChartTheme } from "../lib/theme";
import { EXPENSE_LABELS, SALES_LABELS, localIsoDate, type DailyRecord, type ViewMode } from "../types";

interface DashboardPageProps {
  days: DailyRecord[];
}

type AnalysisGroup = "stock" | "expenses" | "sales" | "credits" | "totals" | "cash" | "notes";
type DashboardSection = "summary" | "evolution" | "breakdown";

interface PeriodTotals {
  salesUsd: number;
  salesLbp: number;
  expensesUsd: number;
  expensesLbp: number;
  salesEquivalent: number;
  expensesEquivalent: number;
  netEquivalent: number;
  liters: number;
}

const emptyTotals: PeriodTotals = {
  salesUsd: 0, salesLbp: 0, expensesUsd: 0, expensesLbp: 0,
  salesEquivalent: 0, expensesEquivalent: 0, netEquivalent: 0, liters: 0,
};

function sumPeriod(days: DailyRecord[]): PeriodTotals {
  return days.reduce(
    (sum, day) => ({
      salesUsd: sum.salesUsd + day.totals.totalSales.usd,
      salesLbp: sum.salesLbp + day.totals.totalSales.lbp,
      expensesUsd: sum.expensesUsd + day.totals.totalExpenses.usd,
      expensesLbp: sum.expensesLbp + day.totals.totalExpenses.lbp,
      salesEquivalent: sum.salesEquivalent + day.totals.salesUsdEquivalent,
      expensesEquivalent: sum.expensesEquivalent + day.totals.expensesUsdEquivalent,
      netEquivalent: sum.netEquivalent + day.totals.netUsdEquivalent,
      liters: sum.liters + day.fuelVolumeSoldL,
    }),
    { ...emptyTotals },
  );
}

/** Variation en % ; `undefined` quand la référence est nulle (rien à comparer). */
function variation(current: number, previous: number): number | undefined {
  if (!previous) return undefined;
  return ((current - previous) / Math.abs(previous)) * 100;
}

function ChartTooltip({ active, payload, label, colors }: any) {
  if (!active || !payload?.length) return null;
  const theme = colors as ChartTheme;
  return (
    <div
      className="chart-tooltip"
      style={{
        background: theme.tooltipBackground,
        color: theme.tooltipText,
        borderColor: theme.tooltipBorder,
      }}
    >
      <strong>{label}</strong>
      {payload.map((item: any) => (
        <span className="tooltip-row" key={`${item.dataKey}-${item.name}`}>
          <i style={{ background: item.color }} />
          <span>{item.name}</span>
          <b>{formatUsd(Number(item.value ?? 0))}</b>
        </span>
      ))}
    </div>
  );
}

export function DashboardPage({ days }: DashboardPageProps) {
  const chart = useChartTheme();
  const now = new Date();
  const latestRecordDate = days.reduce((latest, day) => (day.recordDate > latest ? day.recordDate : latest), "");
  const anchorDate = latestRecordDate || localIsoDate(now);
  const anchorYear = Number(anchorDate.slice(0, 4));
  const anchorMonth = Number(anchorDate.slice(5, 7));
  const years = useMemo(
    () => [...new Set(days.map((day) => Number(day.recordDate.slice(0, 4))))].sort((a, b) => b - a),
    [days],
  );
  const fallbackYear = years.includes(anchorYear) ? anchorYear : years[0] || now.getFullYear();

  const [view, setView] = useState<ViewMode>("month");
  const [year, setYear] = useState(fallbackYear);
  const [month, setMonth] = useState(anchorMonth);
  const [week, setWeek] = useState(isoWeek(anchorDate));
  const [selectedDay, setSelectedDay] = useState("");
  const [group, setGroup] = useState<AnalysisGroup>("stock");
  const [section, setSection] = useState<DashboardSection>("summary");
  const [compare, setCompare] = useState(false);

  const yearDays = useMemo(() => days.filter((day) => Number(day.recordDate.slice(0, 4)) === year), [days, year]);
  const availableWeeks = useMemo(
    () => [...new Set(yearDays.map((day) => isoWeek(day.recordDate)))].sort((a, b) => b - a),
    [yearDays],
  );
  const effectiveWeek = availableWeeks.includes(week) ? week : availableWeeks[0];
  const monthDays = useMemo(
    () => yearDays.filter((day) => Number(day.recordDate.slice(5, 7)) === month),
    [yearDays, month],
  );
  const availableDates = monthDays.map((day) => day.recordDate).sort().reverse();
  const effectiveDay = selectedDay && availableDates.includes(selectedDay) ? selectedDay : availableDates[0] || "";

  const periodDays = useMemo(() => {
    if (view === "year") return yearDays;
    if (view === "week") return yearDays.filter((day) => isoWeek(day.recordDate) === effectiveWeek);
    if (view === "day") return monthDays.filter((day) => day.recordDate === effectiveDay);
    return monthDays;
  }, [view, yearDays, monthDays, effectiveWeek, effectiveDay]);

  /* --- Période de comparaison : la précédente de même nature --------------- */

  const comparison = useMemo(() => {
    if (view === "year") {
      return { days: days.filter((day) => Number(day.recordDate.slice(0, 4)) === year - 1), label: `${year - 1}` };
    }
    if (view === "month") {
      const previousMonth = month === 1 ? 12 : month - 1;
      const previousYear = month === 1 ? year - 1 : year;
      return {
        days: days.filter(
          (day) => Number(day.recordDate.slice(0, 4)) === previousYear
            && Number(day.recordDate.slice(5, 7)) === previousMonth,
        ),
        label: `${monthNames[previousMonth - 1].toLocaleLowerCase("fr")} ${previousYear}`,
      };
    }
    if (view === "week") {
      if (effectiveWeek == null) return { days: [], label: "—" };
      if (effectiveWeek > 1) {
        return {
          days: yearDays.filter((day) => isoWeek(day.recordDate) === effectiveWeek - 1),
          label: `semaine ${String(effectiveWeek - 1).padStart(2, "0")}`,
        };
      }
      const previousYearDays = days.filter((day) => Number(day.recordDate.slice(0, 4)) === year - 1);
      if (!previousYearDays.length) return { days: [], label: "—" };
      const lastWeek = Math.max(...previousYearDays.map((day) => isoWeek(day.recordDate)));
      return {
        days: previousYearDays.filter((day) => isoWeek(day.recordDate) === lastWeek),
        label: `semaine ${String(lastWeek).padStart(2, "0")} · ${year - 1}`,
      };
    }
    const previousDate = days
      .map((day) => day.recordDate)
      .filter((date) => date < effectiveDay)
      .sort()
      .at(-1);
    return previousDate
      ? { days: days.filter((day) => day.recordDate === previousDate), label: formatDate(previousDate) }
      : { days: [], label: "—" };
  }, [days, view, year, month, effectiveWeek, effectiveDay, yearDays]);

  const totals = useMemo(() => sumPeriod(periodDays), [periodDays]);
  const previousTotals = useMemo(() => sumPeriod(comparison.days), [comparison.days]);
  const comparisonActive = compare && comparison.days.length > 0;

  const delta = (current: number, previous: number, higherIsBetter = true): MetricDelta | undefined => {
    if (!comparisonActive) return undefined;
    const percentage = variation(current, previous);
    if (percentage === undefined) return undefined;
    return { percentage, label: `vs ${comparison.label}`, higherIsBetter };
  };

  /* --- Séries -------------------------------------------------------------- */

  const seriesFor = (source: DailyRecord[]) => {
    if (view === "year") {
      const grouped = new Map<number, { label: string; sales: number; expenses: number; net: number }>();
      source.forEach((day) => {
        const monthIndex = Number(day.recordDate.slice(5, 7));
        const current = grouped.get(monthIndex)
          || { label: monthNames[monthIndex - 1].slice(0, 4), sales: 0, expenses: 0, net: 0 };
        current.sales += day.totals.salesUsdEquivalent;
        current.expenses += day.totals.expensesUsdEquivalent;
        current.net += day.totals.netUsdEquivalent;
        grouped.set(monthIndex, current);
      });
      return [...grouped.entries()].sort(([a], [b]) => a - b).map(([, value]) => value);
    }
    return [...source].sort((a, b) => a.recordDate.localeCompare(b.recordDate)).map((day) => ({
      label: view === "day" ? formatDate(day.recordDate) : day.recordDate.slice(8, 10),
      sales: day.totals.salesUsdEquivalent,
      expenses: day.totals.expensesUsdEquivalent,
      net: day.totals.netUsdEquivalent,
    }));
  };

  const chartData = useMemo(() => seriesFor(periodDays), [periodDays, view]);
  const comparisonSeries = useMemo(
    () => (comparisonActive ? seriesFor(comparison.days) : []),
    [comparisonActive, comparison.days, view],
  );

  /** Les deux périodes sont alignées rang par rang (jour 1 vs jour 1, mois 1 vs mois 1). */
  const overlaidData = useMemo(
    () => chartData.map((point, index) => ({
      ...point,
      salesPrevious: comparisonSeries[index]?.sales,
      expensesPrevious: comparisonSeries[index]?.expenses,
      netPrevious: comparisonSeries[index]?.net,
    })),
    [chartData, comparisonSeries],
  );

  const stockSeries = useMemo(
    () => [...periodDays]
      .sort((a, b) => a.recordDate.localeCompare(b.recordDate))
      .map((day) => ({
        label: view === "year" ? day.recordDate.slice(5, 10) : day.recordDate.slice(8, 10),
        stock: day.actualStockEndL,
        capacite: day.tankCapacityL || undefined,
      })),
    [periodDays, view],
  );

  const comparisonBars = useMemo(
    () => [
      { label: "Ventes", actuel: totals.salesEquivalent, precedent: previousTotals.salesEquivalent },
      { label: "Dépenses", actuel: totals.expensesEquivalent, precedent: previousTotals.expensesEquivalent },
      { label: "Résultat", actuel: totals.netEquivalent, precedent: previousTotals.netEquivalent },
    ],
    [totals, previousTotals],
  );

  const expenseBreakdown = useMemo(
    () => (Object.keys(EXPENSE_LABELS) as (keyof DailyRecord["expenses"])[])
      .map((key) => ({
        name: EXPENSE_LABELS[key],
        value: periodDays.reduce((sum, day) => sum + toUsd(day.expenses[key], day.exchangeRate), 0),
      }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value),
    [periodDays],
  );
  const expenseTotal = expenseBreakdown.reduce((sum, item) => sum + item.value, 0);

  const periodLabel = view === "year"
    ? `Année ${year}`
    : view === "week"
      ? `Semaine ${String(effectiveWeek ?? "—").padStart(2, "0")} · ${year}`
      : view === "day"
        ? effectiveDay ? formatDate(effectiveDay) : "Aucune journée"
        : `${monthNames[month - 1]} ${year}`;

  const maxResult = Math.max(totals.salesEquivalent, totals.expensesEquivalent, Math.abs(totals.netEquivalent), 1);
  const resultWidth = Math.min((Math.abs(totals.netEquivalent) / maxResult) * 50, 50);
  const granularity = view === "year" ? "un mois" : view === "day" ? "la journée" : "une journée";

  if (!days.length) {
    return (
      <div className="empty-state large">
        <Gauge size={42} />
        <h2>Le tableau de bord attend sa première journée</h2>
        <p>Enregistrez une clôture pour faire apparaître les indicateurs et graphiques.</p>
      </div>
    );
  }

  const axisProps = { axisLine: false, tickLine: false, tick: { fill: chart.tick, fontSize: 11 } } as const;
  const tooltip = <Tooltip content={<ChartTooltip colors={chart} />} cursor={{ fill: chart.grid, fillOpacity: .45 }} />;

  return (
    <div className="page-stack">
      <div className="page-intro dashboard-intro">
        <div>
          <span className="eyebrow">PILOTAGE & ANALYSE</span>
          <h2>{periodLabel}</h2>
          <p>Les montants LL sont convertis avec le taux historique propre à chaque journée.</p>
        </div>
        <div className="dashboard-toolbar">
          <button
            type="button"
            className={`compare-switch ${comparisonActive ? "on" : ""}`}
            aria-pressed={compare}
            onClick={() => setCompare((value) => !value)}
          >
            <span className="compare-switch__box" aria-hidden="true">{compare && <Check size={12} strokeWidth={3.5} />}</span>
            <GitCompareArrows size={15} aria-hidden="true" />
            Comparer
          </button>
          <div className="period-filters">
            <select value={view} onChange={(event) => setView(event.target.value as ViewMode)} aria-label="Granularité">
              <option value="day">Jour</option>
              <option value="week">Semaine</option>
              <option value="month">Mois</option>
              <option value="year">Année</option>
            </select>
            <select value={year} onChange={(event) => setYear(Number(event.target.value))} aria-label="Année">
              {years.map((item) => <option key={item}>{item}</option>)}
            </select>
            {(view === "month" || view === "day") && (
              <select value={month} onChange={(event) => setMonth(Number(event.target.value))} aria-label="Mois">
                {monthNames.map((name, index) => <option value={index + 1} key={name}>{name}</option>)}
              </select>
            )}
            {view === "week" && (
              <select value={effectiveWeek ?? ""} onChange={(event) => setWeek(Number(event.target.value))} aria-label="Semaine">
                {availableWeeks.map((item) => <option value={item} key={item}>Semaine {String(item).padStart(2, "0")}</option>)}
              </select>
            )}
            {view === "day" && (
              <select value={effectiveDay} onChange={(event) => setSelectedDay(event.target.value)} aria-label="Journée">
                {availableDates.map((date) => <option value={date} key={date}>{formatDate(date)}</option>)}
              </select>
            )}
          </div>
        </div>
      </div>

      {!periodDays.length ? (
        <div className="empty-state">
          <CalendarDays size={34} />
          <h3>Aucune donnée pour cette période</h3>
          <p>Choisissez une autre période ou enregistrez une nouvelle journée.</p>
        </div>
      ) : (
        <>
          {compare && !comparison.days.length && (
            <div className="compare-note">
              <GitCompareArrows size={17} aria-hidden="true" />
              <span><strong>Comparaison indisponible.</strong> Aucune donnée enregistrée sur la période précédente.</span>
            </div>
          )}
          {comparisonActive && periodDays.length !== comparison.days.length && (
            <div className="compare-note">
              <GitCompareArrows size={17} aria-hidden="true" />
              <span>
                <strong>Périodes de durées différentes.</strong> {periodDays.length} journée{periodDays.length > 1 ? "s" : ""} enregistrée
                {periodDays.length > 1 ? "s" : ""} contre {comparison.days.length} sur {comparison.label} : les écarts en % sont à lire avec cette réserve.
              </span>
            </div>
          )}

          <div className="view-tabs" role="tablist" aria-label="Sections du tableau de bord">
            <button role="tab" aria-selected={section === "summary"} className={section === "summary" ? "active" : ""} onClick={() => setSection("summary")}>Synthèse</button>
            <button role="tab" aria-selected={section === "evolution"} className={section === "evolution" ? "active" : ""} onClick={() => setSection("evolution")}>Évolution</button>
            <button role="tab" aria-selected={section === "breakdown"} className={section === "breakdown" ? "active" : ""} onClick={() => setSection("breakdown")}>Répartition</button>
          </div>

          {section === "summary" && (
            <>
              <div className="metrics-grid four">
                <MetricCard
                  label="Ventes équiv. USD" value={formatUsd(totals.salesEquivalent)}
                  detail={`${formatUsd(totals.salesUsd)} + ${formatLbp(totals.salesLbp)}`}
                  tone="green" icon={ArrowUpRight}
                  delta={delta(totals.salesEquivalent, previousTotals.salesEquivalent)}
                />
                <MetricCard
                  label="Dépenses équiv. USD" value={formatUsd(totals.expensesEquivalent)}
                  detail={`${formatUsd(totals.expensesUsd)} + ${formatLbp(totals.expensesLbp)}`}
                  tone="red" icon={ArrowDownRight}
                  delta={delta(totals.expensesEquivalent, previousTotals.expensesEquivalent, false)}
                />
                <MetricCard
                  label="Résultat net" value={formatUsd(totals.netEquivalent)}
                  detail={`${totals.salesEquivalent ? formatNumber((totals.netEquivalent / totals.salesEquivalent) * 100, 1) : "0,0"} % de marge`}
                  tone={totals.netEquivalent >= 0 ? "green" : "red"} icon={TrendingUp}
                  delta={delta(totals.netEquivalent, previousTotals.netEquivalent)}
                />
                <MetricCard
                  label="Volume vendu" value={`${formatNumber(totals.liters)} L`}
                  detail={`${periodDays.length} journée${periodDays.length > 1 ? "s" : ""}`}
                  tone="blue" icon={Droplets}
                  delta={delta(totals.liters, previousTotals.liters)}
                />
              </div>

              <section className="chart-card result-card">
                <div className="chart-heading">
                  <div><span className="eyebrow">LECTURE IMMÉDIATE</span><h3>Résultat de la période</h3></div>
                  <strong className={totals.netEquivalent >= 0 ? "positive-text" : "negative-text"}>{formatUsd(totals.netEquivalent)}</strong>
                </div>
                <div className="result-axis">
                  <div className="result-half negative-half">
                    {totals.netEquivalent < 0 && <div className="result-fill negative" style={{ width: `${resultWidth * 2}%` }} />}
                  </div>
                  <div className="axis-zero" />
                  <div className="result-half positive-half">
                    {totals.netEquivalent >= 0 && <div className="result-fill positive" style={{ width: `${resultWidth * 2}%` }} />}
                  </div>
                </div>
                <div className="axis-labels"><span>Négatif</span><span>0</span><span>Positif</span></div>
              </section>

              {comparisonActive && (
                <section className="chart-card">
                  <div className="chart-heading">
                    <div>
                      <span className="eyebrow">COMPARAISON</span>
                      <h3>{periodLabel} vs {comparison.label}</h3>
                      <p>
                        Totaux en équivalent USD · {periodDays.length} journée{periodDays.length > 1 ? "s" : ""} contre{" "}
                        {comparison.days.length} journée{comparison.days.length > 1 ? "s" : ""} de référence.
                      </p>
                    </div>
                    <div className="mini-legend">
                      <span><i style={{ background: chart.sales }} /> Période actuelle</span>
                      <span><i style={{ background: chart.salesCompare }} /> Période précédente</span>
                    </div>
                  </div>
                  <div className="chart-container">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={comparisonBars} barGap={2} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                        <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={chart.grid} />
                        <XAxis dataKey="label" {...axisProps} />
                        <YAxis {...axisProps} tickFormatter={(value) => `$${formatNumber(value)}`} />
                        {tooltip}
                        <ReferenceLine y={0} stroke={chart.axis} />
                        <Bar dataKey="precedent" name="Période précédente" fill={chart.salesCompare} radius={[4, 4, 0, 0]} />
                        <Bar dataKey="actuel" name="Période actuelle" fill={chart.sales} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}

              <section className="chart-card">
                <div className="chart-heading">
                  <div>
                    <h3>Revenus vs dépenses</h3>
                    <p>Chaque barre représente {granularity}.</p>
                  </div>
                  <div className="mini-legend">
                    <span><i style={{ background: chart.sales }} /> Revenus</span>
                    <span><i style={{ background: chart.expenses }} /> Dépenses</span>
                  </div>
                </div>
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} barGap={2} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                      <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={chart.grid} />
                      <XAxis dataKey="label" {...axisProps} minTickGap={12} />
                      <YAxis {...axisProps} tickFormatter={(value) => `$${formatNumber(value)}`} />
                      {tooltip}
                      <Bar dataKey="sales" name="Revenus" fill={chart.sales} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="expenses" name="Dépenses" fill={chart.expenses} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>

              {view === "day" && periodDays[0] && <DailyDetail day={periodDays[0]} />}
            </>
          )}

          {section === "evolution" && (
            <>
              {view !== "day" && (
                <section className="chart-card">
                  <div className="chart-heading">
                    <div>
                      <h3>Évolution financière</h3>
                      <p>
                        Revenus, dépenses et résultat net en équivalent USD
                        {comparisonActive ? ` — en pointillés, ${comparison.label} aligné rang par rang.` : "."}
                      </p>
                    </div>
                    <div className="mini-legend">
                      <span><i style={{ background: chart.sales }} /> Revenus</span>
                      <span><i style={{ background: chart.expenses }} /> Dépenses</span>
                      <span><i style={{ background: chart.net }} /> Résultat</span>
                      {comparisonActive && <span style={{ color: chart.tick }}><i className="dashed" /> Période préc.</span>}
                    </div>
                  </div>
                  <div className="chart-container line-large">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={overlaidData} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                        <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={chart.grid} />
                        <XAxis dataKey="label" {...axisProps} minTickGap={12} />
                        <YAxis {...axisProps} tickFormatter={(value) => `$${formatNumber(value)}`} />
                        {tooltip}
                        <ReferenceLine y={0} stroke={chart.axis} />
                        {comparisonActive && (
                          <>
                            <Line type="monotone" dataKey="salesPrevious" name="Revenus (préc.)" stroke={chart.salesCompare} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
                            <Line type="monotone" dataKey="expensesPrevious" name="Dépenses (préc.)" stroke={chart.expensesCompare} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
                            <Line type="monotone" dataKey="netPrevious" name="Résultat (préc.)" stroke={chart.netCompare} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
                          </>
                        )}
                        <Line type="monotone" dataKey="sales" name="Revenus" stroke={chart.sales} strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: chart.sales }} activeDot={{ r: 5 }} />
                        <Line type="monotone" dataKey="expenses" name="Dépenses" stroke={chart.expenses} strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: chart.expenses }} activeDot={{ r: 5 }} />
                        <Line type="monotone" dataKey="net" name="Résultat" stroke={chart.net} strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: chart.net }} activeDot={{ r: 5 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}

              <section className="chart-card">
                <div className="chart-heading">
                  <div>
                    <h3>Évolution du stock d’essence</h3>
                    <p>Niveau réel en fin de journée, rapporté à la capacité de la cuve.</p>
                  </div>
                  <div className="mini-legend">
                    <span><i style={{ background: chart.sales }} /> Stock disponible</span>
                    <span style={{ color: chart.tick }}><i className="dashed" /> Capacité</span>
                  </div>
                </div>
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={stockSeries} margin={{ top: 8, right: 8, bottom: 0, left: -4 }}>
                      <defs>
                        <linearGradient id="stockFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={chart.sales} stopOpacity={chart.areaOpacity} />
                          <stop offset="100%" stopColor={chart.sales} stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={chart.grid} />
                      <XAxis dataKey="label" {...axisProps} minTickGap={12} />
                      <YAxis {...axisProps} tickFormatter={(value) => `${formatNumber(value)} L`} />
                      <Tooltip
                        contentStyle={{ background: chart.tooltipBackground, color: chart.tooltipText, border: `1px solid ${chart.tooltipBorder}`, borderRadius: 11 }}
                        labelStyle={{ color: chart.tooltipText }}
                        itemStyle={{ color: chart.tooltipText }}
                        formatter={(value: any) => `${formatNumber(Number(value ?? 0))} L`}
                      />
                      <Area type="monotone" dataKey="stock" name="Stock disponible" stroke={chart.sales} strokeWidth={2} fill="url(#stockFill)" />
                      <Line type="monotone" dataKey="capacite" name="Capacité" stroke={chart.tick} strokeWidth={1.5} strokeDasharray="5 4" dot={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </section>
            </>
          )}

          {section === "breakdown" && (
            <>
              <section className="chart-card">
                <div className="chart-heading">
                  <div><h3>Répartition des dépenses</h3><p>Valeurs consolidées en équivalent USD sur la période.</p></div>
                  <strong>{formatUsd(expenseTotal)}</strong>
                </div>
                {expenseBreakdown.length ? (
                  <div className="chart-grid wide-left">
                    <div className="chart-container">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={expenseBreakdown} dataKey="value" nameKey="name"
                            innerRadius="55%" outerRadius="82%" paddingAngle={2} stroke={chart.surface} strokeWidth={2}
                          >
                            {expenseBreakdown.map((item, index) => (
                              <Cell key={item.name} fill={chart.categorical[index % chart.categorical.length]} />
                            ))}
                          </Pie>
                          <Tooltip
                            content={<ChartTooltip colors={chart} />}
                            formatter={(value: any) => formatUsd(Number(value ?? 0))}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    {/* Table de relief : l'identité ne repose jamais sur la seule couleur. */}
                    <div className="detail-columns" style={{ marginTop: 0, gridTemplateColumns: "1fr" }}>
                      <div>
                        <h4>Détail par poste</h4>
                        {expenseBreakdown.map((item, index) => (
                          <div className="detail-row" key={item.name}>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                              <i style={{ width: 10, height: 10, borderRadius: 3, background: chart.categorical[index % chart.categorical.length] }} />
                              {item.name}
                            </span>
                            <strong>
                              {formatUsd(item.value)}
                              <small style={{ display: "block", color: "var(--text-muted)", fontWeight: 500 }}>
                                {formatNumber(expenseTotal ? (item.value / expenseTotal) * 100 : 0, 1)} %
                              </small>
                            </strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : <div className="chart-empty">Aucune dépense sur cette période.</div>}
              </section>

              <section className="chart-card">
                <div className="chart-heading group-heading">
                  <div><h3>Analyse par groupe</h3><p>Explorez chaque partie de l’activité sans surcharger l’écran.</p></div>
                  <select value={group} onChange={(event) => setGroup(event.target.value as AnalysisGroup)} aria-label="Groupe analysé">
                    <option value="stock">Stock &amp; change</option>
                    <option value="expenses">Dépenses</option>
                    <option value="sales">Ventes</option>
                    <option value="credits">Crédits</option>
                    <option value="totals">Totaux</option>
                    <option value="cash">Caisses</option>
                    <option value="notes">Notes</option>
                  </select>
                </div>
                <GroupAnalysis group={group} days={periodDays} chart={chart} />
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}

function GroupAnalysis({ group, days, chart }: { group: AnalysisGroup; days: DailyRecord[]; chart: ChartTheme }) {
  const axisProps = { axisLine: false, tickLine: false, tick: { fill: chart.tick, fontSize: 11 } } as const;

  if (group === "notes") {
    const notes = days.filter((day) => day.notes.trim());
    return notes.length ? (
      <div className="notes-list">
        {notes.map((day) => <div key={day.recordDate}><strong>{formatDate(day.recordDate)}</strong><p>{day.notes}</p></div>)}
      </div>
    ) : <div className="chart-empty">Aucune note sur cette période.</div>;
  }

  if (group === "stock") {
    const stockData = [...days]
      .sort((a, b) => a.recordDate.localeCompare(b.recordDate))
      .map((day) => ({
        label: formatDate(day.recordDate),
        reel: day.actualStockEndL,
        theorique: day.totals.theoreticalStockEndL,
      }));
    return (
      <>
        <div className="mini-legend" style={{ marginBottom: 10 }}>
          <span><i style={{ background: chart.net }} /> Stock théorique</span>
          <span><i style={{ background: chart.sales }} /> Stock réel</span>
        </div>
        <div className="chart-container group-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stockData} margin={{ top: 8, right: 8, bottom: 0, left: -4 }}>
              <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={chart.grid} />
              <XAxis dataKey="label" {...axisProps} minTickGap={12} />
              <YAxis {...axisProps} tickFormatter={(value) => `${formatNumber(value)} L`} />
              <Tooltip
                contentStyle={{ background: chart.tooltipBackground, color: chart.tooltipText, border: `1px solid ${chart.tooltipBorder}`, borderRadius: 11 }}
                labelStyle={{ color: chart.tooltipText }}
                itemStyle={{ color: chart.tooltipText }}
                formatter={(value: any) => `${formatNumber(Number(value ?? 0), 1)} L`}
              />
              <Line type="monotone" dataKey="theorique" name="Stock théorique" stroke={chart.net} strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: chart.net }} />
              <Line type="monotone" dataKey="reel" name="Stock réel" stroke={chart.sales} strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: chart.sales }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </>
    );
  }

  let data: { label: string; value: number }[] = [];
  if (group === "expenses") {
    data = (Object.keys(EXPENSE_LABELS) as (keyof DailyRecord["expenses"])[]).map((key) => ({
      label: EXPENSE_LABELS[key],
      value: days.reduce((sum, day) => sum + toUsd(day.expenses[key], day.exchangeRate), 0),
    }));
  } else if (group === "sales") {
    data = (Object.keys(SALES_LABELS) as (keyof DailyRecord["sales"])[]).map((key) => ({
      label: SALES_LABELS[key],
      value: days.reduce((sum, day) => sum + toUsd(day.sales[key], day.exchangeRate), 0),
    }));
    data.push({ label: "Ventes à crédit", value: days.reduce((sum, day) => sum + day.totals.creditSoldUsdEquivalent, 0) });
  } else if (group === "credits") {
    data = [
      { label: "Crédits vendus", value: days.reduce((sum, day) => sum + day.totals.creditSoldUsdEquivalent, 0) },
      { label: "Crédits encaissés", value: days.reduce((sum, day) => sum + day.totals.creditCollectedUsdEquivalent, 0) },
    ];
  } else if (group === "totals") {
    data = [
      { label: "Ventes", value: days.reduce((sum, day) => sum + day.totals.salesUsdEquivalent, 0) },
      { label: "Dépenses", value: days.reduce((sum, day) => sum + day.totals.expensesUsdEquivalent, 0) },
      { label: "Résultat", value: days.reduce((sum, day) => sum + day.totals.netUsdEquivalent, 0) },
    ];
  } else if (group === "cash") {
    data = days.map((day) => ({ label: formatDate(day.recordDate), value: toUsd(day.totals.cashVariance, day.exchangeRate) }));
  }

  return (
    <div className="chart-container group-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 25, right: 12, top: 6, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 5" horizontal={false} stroke={chart.grid} />
          <XAxis type="number" {...axisProps} tickFormatter={(value) => `$${formatNumber(value)}`} />
          <YAxis type="category" dataKey="label" width={125} {...axisProps} />
          <Tooltip
            cursor={{ fill: chart.grid, fillOpacity: .45 }}
            contentStyle={{ background: chart.tooltipBackground, color: chart.tooltipText, border: `1px solid ${chart.tooltipBorder}`, borderRadius: 11 }}
            labelStyle={{ color: chart.tooltipText }}
            itemStyle={{ color: chart.tooltipText }}
            formatter={(value: any) => formatUsd(Number(value ?? 0))}
          />
          <ReferenceLine x={0} stroke={chart.axis} />
          <Bar dataKey="value" name="Équivalent USD" radius={[0, 4, 4, 0]}>
            {data.map((item) => <Cell key={item.label} fill={item.value < 0 ? chart.expenses : chart.sales} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function DailyDetail({ day }: { day: DailyRecord }) {
  return (
    <section className="detail-card">
      <div className="section-heading">
        <div>
          <h3>Détail complet du {formatDate(day.recordDate)}</h3>
          <p>Taux utilisé : 1 USD = {formatNumber(day.exchangeRate)} LL</p>
        </div>
      </div>
      <div className="metrics-grid four compact-metrics">
        <MetricCard label="Stock ouverture" value={`${formatNumber(day.openingStockL)} L`} />
        <MetricCard label="Entrées carburant" value={`${formatNumber(day.fuelInputL)} L`} />
        <MetricCard label="Stock théorique" value={`${formatNumber(day.totals.theoreticalStockEndL)} L`} tone="blue" />
        <MetricCard label="Écart stock" value={`${formatNumber(day.totals.stockVarianceL, 1)} L`} tone={Math.abs(day.totals.stockVarianceL) < 0.01 ? "green" : "red"} />
      </div>
      <div className="detail-columns">
        <div>
          <h4>Ventes</h4>
          {(Object.keys(SALES_LABELS) as (keyof DailyRecord["sales"])[]).map((key) => (
            <div className="detail-row" key={key}><span>{SALES_LABELS[key]}</span><strong>{formatUsd(day.sales[key].usd)} · {formatLbp(day.sales[key].lbp)}</strong></div>
          ))}
        </div>
        <div>
          <h4>Dépenses</h4>
          {(Object.keys(EXPENSE_LABELS) as (keyof DailyRecord["expenses"])[]).map((key) => (
            <div className="detail-row" key={key}><span>{EXPENSE_LABELS[key]}</span><strong>{formatUsd(day.expenses[key].usd)} · {formatLbp(day.expenses[key].lbp)}</strong></div>
          ))}
        </div>
      </div>
      {(day.creditSales.length > 0 || day.creditPayments.length > 0) && (
        <div className="detail-columns">
          <ClientDetail title="Crédits vendus" entries={day.creditSales} />
          <ClientDetail title="Crédits encaissés" entries={day.creditPayments} />
        </div>
      )}
      {day.notes && <div className="note-box"><strong>Notes</strong><p>{day.notes}</p></div>}
    </section>
  );
}

function ClientDetail({ title, entries }: { title: string; entries: DailyRecord["creditSales"] }) {
  return (
    <div>
      <h4>{title}</h4>
      {entries.length ? entries.map((entry, index) => (
        <div className="detail-row" key={`${entry.clientName}-${index}`}>
          <span>{entry.clientName}<small>{entry.note}</small></span>
          <strong>{entry.currency === "USD" ? formatUsd(entry.amount) : formatLbp(entry.amount)}</strong>
        </div>
      )) : <p className="muted">Aucune ligne</p>}
    </div>
  );
}
