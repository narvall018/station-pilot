import {
  Banknote,
  CheckCircle2,
  CircleDollarSign,
  Droplets,
  Fuel,
  Loader2,
  ReceiptText,
  Save,
  ShoppingCart,
  WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ClientTable, MoneyFields, NumberField } from "../components/FormControls";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { calculateTotals } from "../lib/calculations";
import { formatDate, formatLbp, formatNumber, formatUsd } from "../lib/format";
import {
  EXPENSE_LABELS,
  SALES_LABELS,
  emptyDay,
  localIsoDate,
  type ClientTransaction,
  type CreditActionRequest,
  type CustomerSummary,
  type DailyInput,
  type DailyRecord,
  type MoneyPair,
} from "../types";

interface EntryPageProps {
  days: DailyRecord[];
  requestedEditDate?: string;
  requestedCreditAction?: CreditActionRequest;
  customers: CustomerSummary[];
  onSaved: (record: DailyRecord) => Promise<void> | void;
}

function cloneInput(record: DailyRecord): DailyInput {
  const { id: _id, totals: _totals, createdAt: _created, updatedAt: _updated, ...input } = record;
  return structuredClone(input);
}

function cleanClientRows(entries: ClientTransaction[], label: string): ClientTransaction[] {
  return entries
    .filter((entry) => entry.clientName.trim() || entry.amount > 0 || entry.note.trim())
    .map((entry) => {
      if (!entry.clientName.trim()) throw new Error(`Le nom du client est obligatoire pour ${label}.`);
      if (entry.amount <= 0) throw new Error(`Le montant doit être positif pour ${entry.clientName}.`);
      return { ...entry, clientName: entry.clientName.trim(), note: entry.note.trim() };
    });
}

export function EntryPage({ days, requestedEditDate, requestedCreditAction, customers, onSaved }: EntryPageProps) {
  const [mode, setMode] = useState<"new" | "edit">("new");
  const [form, setForm] = useState<DailyInput>(() => emptyDay());
  const [selectedDate, setSelectedDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<DailyRecord | null>(null);
  const processedCreditAction = useRef(0);

  const sortedDays = useMemo(
    () => [...days].sort((a, b) => b.recordDate.localeCompare(a.recordDate)),
    [days],
  );

  const loadDate = (date: string) => {
    const record = days.find((item) => item.recordDate === date);
    if (!record) return;
    setSelectedDate(date);
    setForm(cloneInput(record));
    setSuccess(null);
    setError("");
  };

  useEffect(() => {
    if (requestedEditDate && days.some((day) => day.recordDate === requestedEditDate)) {
      setMode("edit");
      loadDate(requestedEditDate);
    }
    // loadDate intentionally derives from the latest days prop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedEditDate, days]);

  useEffect(() => {
    if (!requestedCreditAction || processedCreditAction.current === requestedCreditAction.key) return;
    processedCreditAction.current = requestedCreditAction.key;
    const today = localIsoDate();
    const existingToday = days.find((day) => day.recordDate === today);
    const base = existingToday ? cloneInput(existingToday) : emptyDay(today);
    const entry: ClientTransaction = {
      customerId: requestedCreditAction.customer.id,
      clientName: requestedCreditAction.customer.name,
      amount: 0,
      currency: "USD",
      note: "",
    };
    const field = requestedCreditAction.type === "credit" ? "creditSales" : "creditPayments";
    base[field] = [...base[field], entry];
    setMode(existingToday ? "edit" : "new");
    setSelectedDate(existingToday?.recordDate || "");
    setForm(base);
    setError("");
    setSuccess(null);
  }, [requestedCreditAction, days]);

  const switchMode = (next: "new" | "edit") => {
    setMode(next);
    setError("");
    setSuccess(null);
    if (next === "new") {
      setSelectedDate("");
      setForm(emptyDay());
    } else if (sortedDays.length) {
      loadDate(sortedDays[0].recordDate);
    }
  };

  const totals = useMemo(() => calculateTotals(form), [form]);
  const update = <K extends keyof DailyInput>(key: K, value: DailyInput[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const updateMoneyGroup = (
    group: "sales" | "expenses",
    key: string,
    value: MoneyPair,
  ) => {
    setForm((current) => ({
      ...current,
      [group]: { ...current[group], [key]: value },
    }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSuccess(null);
    try {
      if (form.tankCapacityL > 0 && form.actualStockEndL > form.tankCapacityL) {
        throw new Error("Le stock réel ne peut pas dépasser la capacité du réservoir.");
      }
      if (totals.theoreticalStockEndL < 0) {
        throw new Error("Le stock théorique est négatif. Vérifiez les litres saisis.");
      }
      const payload: DailyInput = {
        ...form,
        creditSales: cleanClientRows(form.creditSales, "une vente à crédit"),
        creditPayments: cleanClientRows(form.creditPayments, "un crédit encaissé"),
        stockValueUsd: form.stockValueUsd || form.actualStockEndL * form.fuelCostUsdPerL,
      };
      setSaving(true);
      const saved = mode === "edit"
        ? await api.updateDay(form.recordDate, payload)
        : await api.createDay(payload);
      setForm(cloneInput(saved));
      setSuccess(saved);
      await onSaved(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Enregistrement impossible.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="page-stack">
      <div className="page-intro">
        <div>
          <span className="eyebrow">CLÔTURE OPÉRATIONNELLE</span>
          <h2>Une saisie rapide, des contrôles immédiats</h2>
          <p>Les montants USD et LL restent séparés. Les graphiques utilisent le taux propre à chaque journée.</p>
        </div>
        <div className="mode-switch" role="group" aria-label="Mode de saisie">
          <button type="button" className={mode === "new" ? "active" : ""} onClick={() => switchMode("new")}>Nouvelle journée</button>
          <button type="button" disabled={!days.length} className={mode === "edit" ? "active" : ""} onClick={() => switchMode("edit")}>Modifier</button>
        </div>
      </div>

      <nav className="form-stepper" aria-label="Accès rapide aux sections du formulaire">
        <a href="#general"><b>1</b><span>Général</span></a>
        <a href="#stock"><b>2</b><span>Stock</span></a>
        <a href="#sales"><b>3</b><span>Ventes</span></a>
        <a href="#credits"><b>4</b><span>Crédits</span></a>
        <a href="#expenses"><b>5</b><span>Dépenses</span></a>
        <a href="#cash"><b>6</b><span>Caisses</span></a>
        <a href="#notes"><b>7</b><span>Notes</span></a>
      </nav>

      {mode === "edit" && (
        <div className="edit-banner">
          <div><strong>Modification protégée</strong><span>Les valeurs existantes sont préchargées.</span></div>
          <select value={selectedDate} onChange={(event) => loadDate(event.target.value)}>
            {sortedDays.map((day) => <option value={day.recordDate} key={day.recordDate}>{formatDate(day.recordDate)}</option>)}
          </select>
        </div>
      )}

      {error && <div className="alert error"><strong>Vérification nécessaire</strong><span>{error}</span></div>}
      {success && (
        <div className="alert success">
          <CheckCircle2 size={22} />
          <div><strong>Journée du {formatDate(success.recordDate)} enregistrée</strong><span>SQLite et les sauvegardes CSV sont synchronisés.</span></div>
        </div>
      )}

      <section className="form-card" id="general">
        <div className="section-heading">
          <div className="section-icon"><CircleDollarSign size={20} /></div>
          <div><h3>Informations générales</h3><p>Date de clôture et taux de conversion du jour.</p></div>
        </div>
        <div className="form-grid two">
          <label className="field">
            <span className="field-label">Date de la journée</span>
            <input type="date" value={form.recordDate} disabled={mode === "edit"} onChange={(event) => update("recordDate", event.target.value)} />
          </label>
          <NumberField label="Taux LL pour 1 USD" value={form.exchangeRate} suffix="LL" onChange={(value) => update("exchangeRate", value)} hint="Exemple : 89 500 signifie 1 USD = 89 500 LL." />
        </div>
      </section>

      <section className="form-card" id="stock">
        <div className="section-heading">
          <div className="section-icon blue"><Droplets size={20} /></div>
          <div><h3>Stock & carburant</h3><p>Rapprochement automatique entre stock théorique et stock réel.</p></div>
        </div>
        <div className="form-grid four">
          <NumberField label="Capacité réservoir" value={form.tankCapacityL} suffix="L" onChange={(value) => update("tankCapacityL", value)} />
          <NumberField label="Stock ouverture" value={form.openingStockL} suffix="L" onChange={(value) => update("openingStockL", value)} />
          <NumberField label="Entrées carburant" value={form.fuelInputL} suffix="L" onChange={(value) => update("fuelInputL", value)} />
          <NumberField label="Essence vendue" value={form.fuelVolumeSoldL} suffix="L" onChange={(value) => update("fuelVolumeSoldL", value)} />
          <NumberField label="Stock réel fin" value={form.actualStockEndL} suffix="L" onChange={(value) => update("actualStockEndL", value)} />
          <NumberField label="Coût USD / litre" value={form.fuelCostUsdPerL} suffix="$" onChange={(value) => update("fuelCostUsdPerL", value)} />
          <NumberField label="Valeur stock USD" value={form.stockValueUsd} suffix="$" onChange={(value) => update("stockValueUsd", value)} hint="Laissez 0 pour calcul automatique." />
          <div className={`computed-field ${Math.abs(totals.stockVarianceL) > 0.01 ? "negative" : "positive"}`}>
            <span>Stock théorique / écart</span>
            <strong>{formatNumber(totals.theoreticalStockEndL, 1)} L</strong>
            <small>Écart : {formatNumber(totals.stockVarianceL, 1)} L</small>
          </div>
        </div>
      </section>

      <section className="form-card" id="sales">
        <div className="section-heading">
          <div className="section-icon"><ShoppingCart size={20} /></div>
          <div><h3>Ventes du jour</h3><p>Chaque activité peut être encaissée simultanément en USD et en LL.</p></div>
        </div>
        <div className="money-table">
          {(Object.keys(SALES_LABELS) as (keyof DailyInput["sales"])[]).map((key) => (
            <MoneyFields key={key} label={SALES_LABELS[key]} value={form.sales[key]} onChange={(value) => updateMoneyGroup("sales", key, value)} />
          ))}
        </div>
      </section>

      <section className="form-card" id="credits">
        <div className="section-heading">
          <div className="section-icon amber"><WalletCards size={20} /></div>
          <div><h3>Crédits clients</h3><p>Distinguez les nouvelles créances des remboursements encaissés.</p></div>
        </div>
        <ClientTable entries={form.creditSales} customers={customers} onChange={(entries) => update("creditSales", entries)} title="Crédits vendus" description="Ventes du jour non encaissées." actionLabel="Ajouter un client" />
        <ClientTable entries={form.creditPayments} customers={customers} onChange={(entries) => update("creditPayments", entries)} title="Crédits encaissés" description="Remboursements reçus aujourd’hui." actionLabel="Ajouter un paiement" />
      </section>

      <section className="form-card" id="expenses">
        <div className="section-heading">
          <div className="section-icon red"><ReceiptText size={20} /></div>
          <div><h3>Dépenses & achats</h3><p>Ventilation complète pour comprendre où part l’argent.</p></div>
        </div>
        <div className="money-table">
          {(Object.keys(EXPENSE_LABELS) as (keyof DailyInput["expenses"])[]).map((key) => (
            <MoneyFields key={key} label={EXPENSE_LABELS[key]} value={form.expenses[key]} onChange={(value) => updateMoneyGroup("expenses", key, value)} />
          ))}
        </div>
      </section>

      <section className="form-card" id="cash">
        <div className="section-heading">
          <div className="section-icon purple"><Banknote size={20} /></div>
          <div><h3>Rapprochement des caisses</h3><p>Ouverture + ventes encaissées + crédits encaissés − dépenses.</p></div>
        </div>
        <div className="cash-grid">
          <MoneyFields label="Caisses à l’ouverture" value={form.cashOpening} onChange={(value) => update("cashOpening", value)} />
          <MoneyFields label="Caisses réelles fin" value={form.cashActualEnd} onChange={(value) => update("cashActualEnd", value)} />
        </div>
        <div className="metrics-grid four compact-metrics">
          <MetricCard label="Théorique USD" value={formatUsd(totals.cashTheoreticalEnd.usd)} tone="blue" />
          <MetricCard label="Écart USD" value={formatUsd(totals.cashVariance.usd)} tone={Math.abs(totals.cashVariance.usd) < 0.01 ? "green" : "red"} />
          <MetricCard label="Théorique LL" value={formatLbp(totals.cashTheoreticalEnd.lbp)} tone="blue" />
          <MetricCard label="Écart LL" value={formatLbp(totals.cashVariance.lbp)} tone={Math.abs(totals.cashVariance.lbp) < 1 ? "green" : "red"} />
        </div>
      </section>

      <section className="form-card" id="notes">
        <div className="section-heading">
          <div className="section-icon neutral"><Fuel size={20} /></div>
          <div><h3>Notes de la journée</h3><p>Livraison, incident, écart expliqué ou information utile.</p></div>
        </div>
        <textarea className="notes-area" value={form.notes} onChange={(event) => update("notes", event.target.value)} placeholder="Événement particulier, livraison, maintenance prévue…" />
      </section>

      <div className="sticky-summary">
        <div className="summary-values">
          <span><small>Ventes</small><strong>{formatUsd(totals.salesUsdEquivalent)}</strong></span>
          <span><small>Dépenses</small><strong>{formatUsd(totals.expensesUsdEquivalent)}</strong></span>
          <span className={totals.netUsdEquivalent >= 0 ? "positive-text" : "negative-text"}><small>Résultat</small><strong>{formatUsd(totals.netUsdEquivalent)}</strong></span>
        </div>
        <button className="button primary save-button" type="submit" disabled={saving}>
          {saving ? <Loader2 className="spin" size={19} /> : <Save size={19} />}
          {mode === "edit" ? "Mettre à jour la journée" : "Enregistrer la journée"}
        </button>
      </div>
    </form>
  );
}
