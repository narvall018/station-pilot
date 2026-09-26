import {
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  HandCoins,
  Loader2,
  Plus,
  Search,
  UserRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { formatDate, formatLbp, formatUsd } from "../lib/format";
import type { CreditActionRequest, CustomerLedger, CustomerSummary, MoneyPair } from "../types";

interface CreditsPageProps {
  customers: CustomerSummary[];
  onAction: (customer: CustomerSummary, type: CreditActionRequest["type"]) => void;
  onNew: () => void;
}

type CreditFilter = "all" | "due" | "paid" | "advance";

const hasDebt = (customer: CustomerSummary) => customer.balance.usd > 0.005 || customer.balance.lbp > 0.5;
const hasAdvance = (customer: CustomerSummary) => customer.balance.usd < -0.005 || customer.balance.lbp < -0.5;
const creditStatus = (customer: CustomerSummary): Exclude<CreditFilter, "all"> => {
  if (hasDebt(customer)) return "due";
  if (hasAdvance(customer)) return "advance";
  return "paid";
};

function StatusBadge({ customer }: { customer: CustomerSummary }) {
  if (creditStatus(customer) === "due") return <span className="credit-status due"><CircleAlert size={13} /> À rembourser</span>;
  if (creditStatus(customer) === "advance") return <span className="credit-status advance"><ArrowDownLeft size={13} /> Avance client</span>;
  return <span className="credit-status paid"><CheckCircle2 size={13} /> Soldé</span>;
}

export function CreditsPage({ customers, onAction, onNew }: CreditsPageProps) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<CreditFilter>("due");
  const [selectedId, setSelectedId] = useState<number>();
  const [ledger, setLedger] = useState<CustomerLedger>();
  const [loadingLedger, setLoadingLedger] = useState(false);
  const [ledgerError, setLedgerError] = useState("");

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("fr");
    return customers
      .filter((customer) => !needle || customer.name.toLocaleLowerCase("fr").includes(needle))
      .filter((customer) => filter === "all" || creditStatus(customer) === filter)
      .sort((a, b) => {
        const aDue = Number(hasDebt(a));
        const bDue = Number(hasDebt(b));
        return bDue - aDue || b.lastActivityDate.localeCompare(a.lastActivityDate) || a.name.localeCompare(b.name, "fr");
      });
  }, [customers, search, filter]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(undefined);
      setLedger(undefined);
      return;
    }
    if (!selectedId || !filtered.some((customer) => customer.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setLoadingLedger(true);
    setLedgerError("");
    api.getCustomerLedger(selectedId)
      .then((result) => { if (active) setLedger(result); })
      .catch((error) => { if (active) setLedgerError(error instanceof Error ? error.message : "Historique indisponible."); })
      .finally(() => { if (active) setLoadingLedger(false); });
    return () => { active = false; };
  }, [selectedId, customers]);

  const totals = customers.reduce((sum, customer) => ({
    usd: sum.usd + Math.max(customer.balance.usd, 0),
    lbp: sum.lbp + Math.max(customer.balance.lbp, 0),
  }), { usd: 0, lbp: 0 });
  const dueCount = customers.filter(hasDebt).length;
  const advanceCount = customers.filter((customer) => creditStatus(customer) === "advance").length;
  const paidCount = customers.filter((customer) => creditStatus(customer) === "paid").length;

  if (!customers.length) {
    return (
      <div className="empty-state large">
        <HandCoins size={43} />
        <h2>Aucun compte client pour le moment</h2>
        <p>Ajoutez un crédit depuis la saisie journalière. Le client apparaîtra ensuite ici avec son solde et tous ses remboursements.</p>
        <button className="button primary" onClick={onNew}><Plus size={17} /> Enregistrer un premier crédit</button>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <div className="page-intro credits-intro">
        <div>
          <span className="eyebrow">COMPTES CLIENTS</span>
          <h2>Qui doit encore de l’argent ?</h2>
          <p>Les crédits et remboursements sont cumulés par client, en conservant séparément USD et LL.</p>
        </div>
        <button className="button primary" onClick={onNew}><Plus size={17} /> Nouvelle opération</button>
      </div>

      <div className="metrics-grid four">
        <MetricCard label="À recevoir — USD" value={formatUsd(totals.usd)} detail={`${dueCount} client${dueCount > 1 ? "s" : ""} débiteur${dueCount > 1 ? "s" : ""}`} tone="red" icon={ArrowUpRight} />
        <MetricCard label="À recevoir — LL" value={formatLbp(totals.lbp)} detail="Sans conversion, montant d’origine" tone="red" icon={ArrowUpRight} />
        <MetricCard label="Clients à rembourser" value={String(dueCount)} detail="Solde USD ou LL positif" tone="amber" icon={CircleAlert} />
        <MetricCard label="Comptes soldés" value={String(paidCount)} detail={`${advanceCount} compte${advanceCount > 1 ? "s" : ""} avec une avance`} tone="green" icon={CheckCircle2} />
      </div>

      <div className="credit-toolbar">
        <div className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Rechercher un client…" /></div>
        <div className="view-tabs">
          <button className={filter === "due" ? "active" : ""} onClick={() => setFilter("due")}>À rembourser ({dueCount})</button>
          <button className={filter === "paid" ? "active" : ""} onClick={() => setFilter("paid")}>Soldés ({paidCount})</button>
          <button className={filter === "advance" ? "active" : ""} onClick={() => setFilter("advance")}>Avances ({advanceCount})</button>
          <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>Tous ({customers.length})</button>
        </div>
      </div>

      {!filtered.length ? (
        <div className="empty-state"><CheckCircle2 size={34} /><h3>Aucun client dans cette vue</h3><p>Modifiez le filtre ou la recherche.</p></div>
      ) : (
        <div className="credit-workspace">
          <section className="customer-list-card">
            <div className="customer-list-heading"><strong>{filtered.length} client{filtered.length > 1 ? "s" : ""}</strong><span>Sélectionnez un compte</span></div>
            <div className="customer-list">
              {filtered.map((customer) => (
                <button key={customer.id} className={selectedId === customer.id ? "customer-item active" : "customer-item"} onClick={() => setSelectedId(customer.id)}>
                  <span className="customer-avatar"><UserRound size={18} /></span>
                  <span className="customer-identity"><strong>{customer.name}</strong><small>{customer.lastActivityDate ? `Dernière opération ${formatDate(customer.lastActivityDate)}` : "Aucune opération"}</small></span>
                  <span className={`customer-balance ${creditStatus(customer)}`}><strong>{formatUsd(customer.balance.usd)}</strong><small>{formatLbp(customer.balance.lbp)}</small></span>
                </button>
              ))}
            </div>
          </section>

          <section className="credit-detail-card">
            {loadingLedger ? (
              <div className="credit-detail-loading"><Loader2 className="spin" size={25} /> Chargement du compte…</div>
            ) : ledgerError ? (
              <div className="alert error"><strong>Historique indisponible</strong><span>{ledgerError}</span></div>
            ) : ledger ? (
              <CustomerDetail ledger={ledger} onAction={onAction} />
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}

function CustomerDetail({ ledger, onAction }: { ledger: CustomerLedger; onAction: CreditsPageProps["onAction"] }) {
  const { customer } = ledger;
  const running: MoneyPair = { usd: 0, lbp: 0 };
  const rows = ledger.entries.map((entry) => {
    const sign = entry.type === "credit" ? 1 : -1;
    if (entry.currency === "USD") running.usd += sign * entry.amount;
    else running.lbp += sign * entry.amount;
    return { ...entry, running: { ...running } };
  }).reverse();

  return (
    <>
      <div className="credit-detail-header">
        <div><span className="eyebrow">COMPTE CLIENT</span><h3>{customer.name}</h3><StatusBadge customer={customer} /></div>
        <div className="credit-detail-actions">
          <button className="button secondary small" onClick={() => onAction(customer, "credit")}><Plus size={15} /> Ajouter un crédit</button>
          <button className="button primary small" onClick={() => onAction(customer, "payment")}><HandCoins size={15} /> Encaisser</button>
        </div>
      </div>

      <div className="credit-balance-grid">
        <div><span>Reste en USD</span><strong className={customer.balance.usd > 0 ? "negative-text" : "positive-text"}>{formatUsd(customer.balance.usd)}</strong></div>
        <div><span>Reste en LL</span><strong className={customer.balance.lbp > 0 ? "negative-text" : "positive-text"}>{formatLbp(customer.balance.lbp)}</strong></div>
        <div><span>Total crédits</span><strong>{formatUsd(customer.totalCredit.usd)} · {formatLbp(customer.totalCredit.lbp)}</strong></div>
        <div><span>Total remboursé</span><strong>{formatUsd(customer.totalPaid.usd)} · {formatLbp(customer.totalPaid.lbp)}</strong></div>
      </div>

      <div className="credit-ledger-heading"><h4>Historique du compte</h4><span>{ledger.entries.length} opération{ledger.entries.length > 1 ? "s" : ""}</span></div>
      <div className="credit-ledger-table">
        <table>
          <thead><tr><th>Date</th><th>Opération</th><th>Montant</th><th>Note</th><th>Solde après opération</th></tr></thead>
          <tbody>
            {rows.map((entry) => (
              <tr key={`${entry.type}-${entry.id}`}>
                <td><strong>{formatDate(entry.recordDate)}</strong></td>
                <td><span className={`ledger-type ${entry.type}`}>{entry.type === "credit" ? "Crédit ajouté" : "Remboursement"}</span></td>
                <td className={entry.type === "credit" ? "negative-text" : "positive-text"}><strong>{entry.currency === "USD" ? formatUsd(entry.amount) : formatLbp(entry.amount)}</strong></td>
                <td>{entry.note || "—"}</td>
                <td>{formatUsd(entry.running.usd)} · {formatLbp(entry.running.lbp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
