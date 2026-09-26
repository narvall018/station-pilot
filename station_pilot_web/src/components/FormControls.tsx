import { Plus, Trash2 } from "lucide-react";
import type { ClientTransaction, Currency, CustomerSummary, MoneyPair } from "../types";

interface NumberFieldProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
  hint?: string;
  disabled?: boolean;
}

export function NumberField({
  label,
  value,
  onChange,
  suffix,
  hint,
  disabled,
}: NumberFieldProps) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <div className="input-wrap">
        <input
          type="number"
          min="0"
          // Un pas chiffré ferait rejeter par le navigateur toute valeur qui n'en
          // est pas un multiple : 9 490 000 LL avec un pas de 100 000, par exemple.
          step="any"
          inputMode="decimal"
          value={Number.isFinite(value) ? value : 0}
          disabled={disabled}
          onChange={(event) => onChange(Number(event.target.value) || 0)}
        />
        {suffix && <span className="input-suffix">{suffix}</span>}
      </div>
      {hint && <small>{hint}</small>}
    </label>
  );
}

interface MoneyFieldsProps {
  label: string;
  value: MoneyPair;
  onChange: (value: MoneyPair) => void;
}

export function MoneyFields({ label, value, onChange }: MoneyFieldsProps) {
  return (
    <div className="money-row">
      <span className="money-label">{label}</span>
      <NumberField
        label="USD"
        value={value.usd}
        suffix="$"
        onChange={(usd) => onChange({ ...value, usd })}
      />
      <NumberField
        label="Livre libanaise"
        value={value.lbp}
        suffix="LL"
        onChange={(lbp) => onChange({ ...value, lbp })}
      />
    </div>
  );
}

interface ClientTableProps {
  entries: ClientTransaction[];
  onChange: (entries: ClientTransaction[]) => void;
  title: string;
  description: string;
  actionLabel: string;
  customers: CustomerSummary[];
}

const blankClient = (): ClientTransaction => ({
  clientName: "",
  amount: 0,
  currency: "USD",
  note: "",
});

export function ClientTable({
  entries,
  onChange,
  title,
  description,
  actionLabel,
  customers,
}: ClientTableProps) {
  const update = (index: number, patch: Partial<ClientTransaction>) => {
    onChange(entries.map((entry, position) => (position === index ? { ...entry, ...patch } : entry)));
  };

  return (
    <div className="client-editor">
      <div className="section-heading compact">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <button type="button" className="button secondary small" onClick={() => onChange([...entries, blankClient()])}>
          <Plus size={16} /> {actionLabel}
        </button>
      </div>
      {!entries.length ? (
        <button type="button" className="empty-action" onClick={() => onChange([blankClient()])}>
          <Plus size={18} /> Ajouter une première ligne
        </button>
      ) : (
        <div className="client-list">
          {entries.map((entry, index) => (
            <div className="client-row" key={`${index}-${entry.id || "new"}`}>
              <label className="field client-name">
                <span className="field-label">Client</span>
                <select
                  value={entry.customerId ? String(entry.customerId) : "new"}
                  onChange={(event) => {
                    if (event.target.value === "new") {
                      update(index, { customerId: undefined, clientName: "" });
                      return;
                    }
                    const customer = customers.find((item) => item.id === Number(event.target.value));
                    if (customer) update(index, { customerId: customer.id, clientName: customer.name });
                  }}
                >
                  <option value="new">+ Nouveau client</option>
                  {customers.map((customer) => <option value={customer.id} key={customer.id}>{customer.name}</option>)}
                </select>
                {!entry.customerId && <input value={entry.clientName} onChange={(event) => update(index, { clientName: event.target.value })} placeholder="Nom du nouveau client" />}
              </label>
              <label className="field client-amount">
                <span className="field-label">Montant</span>
                <input type="number" min="0" step="any" inputMode="decimal" value={entry.amount} onChange={(event) => update(index, { amount: Number(event.target.value) || 0 })} />
              </label>
              <label className="field client-currency">
                <span className="field-label">Devise</span>
                <select value={entry.currency} onChange={(event) => update(index, { currency: event.target.value as Currency })}>
                  <option value="USD">USD</option>
                  <option value="LBP">LL</option>
                </select>
              </label>
              <label className="field client-note">
                <span className="field-label">Note</span>
                <input value={entry.note} onChange={(event) => update(index, { note: event.target.value })} placeholder="Référence facultative" />
              </label>
              <button type="button" className="icon-button danger" title="Supprimer" onClick={() => onChange(entries.filter((_, position) => position !== index))}>
                <Trash2 size={17} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
