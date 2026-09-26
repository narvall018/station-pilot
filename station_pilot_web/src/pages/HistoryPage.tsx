import { AlertTriangle, Download, FileSpreadsheet, Loader2, Pencil, Search, ShieldCheck, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { csvEscape, formatDate, formatLbp, formatNumber, formatUsd, monthNames } from "../lib/format";
import { EXPENSE_LABELS, SALES_LABELS, type DailyRecord } from "../types";

interface HistoryPageProps {
  days: DailyRecord[];
  onEdit: (date: string) => void;
  onDeleted: () => Promise<void> | void;
}

type HistoryView = "summary" | "complete" | "ledger";

function downloadBlob(content: BlobPart, fileName: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const columns = Object.keys(rows[0]);
  return `\uFEFF${[
    columns.map(csvEscape).join(","),
    ...rows.map((row) => columns.map((column) => csvEscape(row[column])).join(",")),
  ].join("\n")}`;
}

function xmlEscape(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function excelCell(value: unknown, header = false): string {
  const type = typeof value === "number" && Number.isFinite(value) ? "Number" : "String";
  return `<Cell${header ? ' ss:StyleID="Header"' : ""}><Data ss:Type="${type}">${xmlEscape(value)}</Data></Cell>`;
}

function excelSheet(name: string, rows: Record<string, unknown>[]): string {
  const safeRows = rows.length ? rows : [{ Information: "Aucune donnée pour la sélection" }];
  const columns = Object.keys(safeRows[0]);
  return `<Worksheet ss:Name="${xmlEscape(name.slice(0, 31))}"><Table>
    <Row>${columns.map((column) => excelCell(column, true)).join("")}</Row>
    ${safeRows.map((row) => `<Row>${columns.map((column) => excelCell(row[column])).join("")}</Row>`).join("\n")}
  </Table><WorksheetOptions xmlns="urn:schemas-microsoft-com:office:excel"><FreezePanes/><FrozenNoSplit/><SplitHorizontal>1</SplitHorizontal><TopRowBottomPane>1</TopRowBottomPane><ActivePane>2</ActivePane></WorksheetOptions></Worksheet>`;
}

function createExcelWorkbook(sheets: { name: string; rows: Record<string, unknown>[] }[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles><Style ss:ID="Default" ss:Name="Normal"><Alignment ss:Vertical="Bottom"/><Font ss:FontName="Aptos" ss:Size="11"/></Style><Style ss:ID="Header"><Font ss:FontName="Aptos" ss:Size="11" ss:Bold="1" ss:Color="#FFFFFF"/><Interior ss:Color="#123C35" ss:Pattern="Solid"/><Alignment ss:Vertical="Center"/></Style></Styles>
 ${sheets.map((sheet) => excelSheet(sheet.name, sheet.rows)).join("\n")}
</Workbook>`;
}

function completeRows(days: DailyRecord[]) {
  return days.map((day) => {
    const row: Record<string, unknown> = {
      Date: day.recordDate,
      "Taux USD/LBP": day.exchangeRate,
      "Stock ouverture L": day.openingStockL,
      "Entrées carburant L": day.fuelInputL,
      "Ventes essence L": day.fuelVolumeSoldL,
      "Stock théorique fin L": day.totals.theoreticalStockEndL,
      "Stock réel fin L": day.actualStockEndL,
      "Écart stock L": day.totals.stockVarianceL,
      "Coût carburant USD/L": day.fuelCostUsdPerL,
      "Valeur stock USD": day.stockValueUsd,
    };
    (Object.keys(day.expenses) as (keyof DailyRecord["expenses"])[]).forEach((key) => {
      row[`${EXPENSE_LABELS[key]} USD`] = day.expenses[key].usd;
      row[`${EXPENSE_LABELS[key]} LBP`] = day.expenses[key].lbp;
    });
    (Object.keys(day.sales) as (keyof DailyRecord["sales"])[]).forEach((key) => {
      row[`${SALES_LABELS[key]} USD`] = day.sales[key].usd;
      row[`${SALES_LABELS[key]} LBP`] = day.sales[key].lbp;
    });
    Object.assign(row, {
      "Crédit vendu USD": day.totals.creditSold.usd,
      "Crédit vendu LBP": day.totals.creditSold.lbp,
      "Crédit encaissé USD": day.totals.creditCollected.usd,
      "Crédit encaissé LBP": day.totals.creditCollected.lbp,
      "Total ventes USD": day.totals.totalSales.usd,
      "Total ventes LBP": day.totals.totalSales.lbp,
      "Total dépenses USD": day.totals.totalExpenses.usd,
      "Total dépenses LBP": day.totals.totalExpenses.lbp,
      "Ventes équiv. USD": day.totals.salesUsdEquivalent,
      "Dépenses équiv. USD": day.totals.expensesUsdEquivalent,
      "Résultat équiv. USD": day.totals.netUsdEquivalent,
      "Ouverture USD": day.cashOpening.usd,
      "Caisse théorique USD": day.totals.cashTheoreticalEnd.usd,
      "Caisse réelle USD": day.cashActualEnd.usd,
      "Écart caisse USD": day.totals.cashVariance.usd,
      "Ouverture LBP": day.cashOpening.lbp,
      "Caisse théorique LBP": day.totals.cashTheoreticalEnd.lbp,
      "Caisse réelle LBP": day.cashActualEnd.lbp,
      "Écart caisse LBP": day.totals.cashVariance.lbp,
      Notes: day.notes,
    });
    return row;
  });
}

function ledgerRows(days: DailyRecord[]) {
  const rows: Record<string, unknown>[] = [];
  const pushMoney = (
    day: DailyRecord,
    type: string,
    category: string,
    detail: string,
    usd: number,
    lbp: number,
  ) => {
    if (usd > 0) rows.push({ Date: day.recordDate, Type: type, Catégorie: category, Détail: detail, Devise: "USD", Montant: usd, "Taux LL/USD": day.exchangeRate, "Équivalent USD": usd });
    if (lbp > 0) rows.push({ Date: day.recordDate, Type: type, Catégorie: category, Détail: detail, Devise: "LBP", Montant: lbp, "Taux LL/USD": day.exchangeRate, "Équivalent USD": lbp / day.exchangeRate });
  };
  days.forEach((day) => {
    (Object.keys(day.sales) as (keyof DailyRecord["sales"])[]).forEach((key) => pushMoney(day, "Vente", SALES_LABELS[key], key === "fuel" ? `${day.fuelVolumeSoldL} L` : "Comptant", day.sales[key].usd, day.sales[key].lbp));
    day.creditSales.forEach((entry) => pushMoney(day, "Vente à crédit", "Crédit client", entry.clientName + (entry.note ? ` — ${entry.note}` : ""), entry.currency === "USD" ? entry.amount : 0, entry.currency === "LBP" ? entry.amount : 0));
    day.creditPayments.forEach((entry) => pushMoney(day, "Crédit encaissé", "Encaissement client", entry.clientName + (entry.note ? ` — ${entry.note}` : ""), entry.currency === "USD" ? entry.amount : 0, entry.currency === "LBP" ? entry.amount : 0));
    (Object.keys(day.expenses) as (keyof DailyRecord["expenses"])[]).forEach((key) => pushMoney(day, "Dépense", EXPENSE_LABELS[key], "", day.expenses[key].usd, day.expenses[key].lbp));
  });
  return rows;
}

export function HistoryPage({ days, onEdit, onDeleted }: HistoryPageProps) {
  const now = new Date();
  const years = [...new Set(days.map((day) => Number(day.recordDate.slice(0, 4))))].sort((a, b) => b - a);
  const [view, setView] = useState<HistoryView>("summary");
  const [year, setYear] = useState<number | "all">("all");
  const [month, setMonth] = useState<number | "all">("all");
  const [search, setSearch] = useState("");
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleteSuccess, setDeleteSuccess] = useState("");

  const filtered = useMemo(() => days
    .filter((day) => year === "all" || Number(day.recordDate.slice(0, 4)) === year)
    .filter((day) => month === "all" || Number(day.recordDate.slice(5, 7)) === month)
    .filter((day) => {
      const needle = search.trim().toLocaleLowerCase("fr");
      if (!needle) return true;
      return day.notes.toLocaleLowerCase("fr").includes(needle)
        || [...day.creditSales, ...day.creditPayments].some((entry) => entry.clientName.toLocaleLowerCase("fr").includes(needle));
    })
    .sort((a, b) => b.recordDate.localeCompare(a.recordDate)), [days, year, month, search]);

  const fullRows = useMemo(() => completeRows(filtered), [filtered]);
  const journal = useMemo(() => ledgerRows(filtered), [filtered]);

  useEffect(() => {
    const existingDates = new Set(days.map((day) => day.recordDate));
    setSelectedDates((current) => new Set([...current].filter((date) => existingDates.has(date))));
  }, [days]);

  const filteredDates = filtered.map((day) => day.recordDate);
  const allFilteredSelected = filteredDates.length > 0 && filteredDates.every((date) => selectedDates.has(date));
  const toggleDate = (date: string) => setSelectedDates((current) => {
    const next = new Set(current);
    if (next.has(date)) next.delete(date);
    else next.add(date);
    return next;
  });
  const toggleAllFiltered = () => setSelectedDates((current) => {
    const next = new Set(current);
    if (allFilteredSelected) filteredDates.forEach((date) => next.delete(date));
    else filteredDates.forEach((date) => next.add(date));
    return next;
  });

  const openDeleteDialog = () => {
    if (!selectedDates.size) return;
    setDeleteError("");
    setDeleteConfirmation("");
    setDeleteDialogOpen(true);
  };

  const confirmDeletion = async () => {
    if (deleteConfirmation !== "SUPPRIMER" || !selectedDates.size) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const result = await api.deleteDays([...selectedDates]);
      setDeleteSuccess(`${result.deletedDates.length} journée${result.deletedDates.length > 1 ? "s ont" : " a"} été supprimée${result.deletedDates.length > 1 ? "s" : ""}. Sauvegarde de sécurité : ${result.backupName}.`);
      setSelectedDates(new Set());
      setDeleteDialogOpen(false);
      setDeleteConfirmation("");
      await onDeleted();
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "Suppression impossible.");
    } finally {
      setDeleting(false);
    }
  };

  const exportExcel = () => {
    const workbook = createExcelWorkbook([
      { name: "Rapport complet", rows: fullRows },
      { name: "Journal ligne par ligne", rows: journal },
      { name: "Crédits vendus", rows: filtered.flatMap((day) => day.creditSales.map((entry) => ({ Date: day.recordDate, Client: entry.clientName, Montant: entry.amount, Devise: entry.currency, Note: entry.note }))) },
      { name: "Crédits encaissés", rows: filtered.flatMap((day) => day.creditPayments.map((entry) => ({ Date: day.recordDate, Client: entry.clientName, Montant: entry.amount, Devise: entry.currency, Note: entry.note }))) },
    ]);
    downloadBlob(`\uFEFF${workbook}`, `station_pilot_${new Date().toISOString().slice(0, 10)}.xls`, "application/vnd.ms-excel;charset=utf-8");
  };

  const currentRows = view === "complete" ? fullRows : view === "ledger" ? journal : filtered.map((day) => ({
    Date: day.recordDate,
    "Taux LL/USD": day.exchangeRate,
    "Litres vendus": day.fuelVolumeSoldL,
    "Stock fin": day.actualStockEndL,
    "Ventes USD": day.totals.totalSales.usd,
    "Ventes LBP": day.totals.totalSales.lbp,
    "Dépenses USD": day.totals.totalExpenses.usd,
    "Dépenses LBP": day.totals.totalExpenses.lbp,
    "Résultat équiv. USD": day.totals.netUsdEquivalent,
  }));

  if (!days.length) return <div className="empty-state large"><FileSpreadsheet size={42} /><h2>Aucun historique pour le moment</h2><p>Les journées enregistrées et leurs exports apparaîtront ici.</p></div>;

  return (
    <div className="page-stack">
      <div className="page-intro history-intro">
        <div><span className="eyebrow">BASE LOCALE & EXPORTS</span><h2>{filtered.length} journée{filtered.length > 1 ? "s" : ""} affichée{filtered.length > 1 ? "s" : ""}</h2><p>Consultez chaque montant d’origine ou le journal comptable normalisé.</p></div>
        <div className="export-actions">
          <button className="button destructive" disabled={!selectedDates.size} onClick={openDeleteDialog}><Trash2 size={17} /> Supprimer {selectedDates.size ? `(${selectedDates.size})` : ""}</button>
          <button className="button secondary" onClick={() => downloadBlob(toCsv(currentRows), `station_${view}_${now.toISOString().slice(0, 10)}.csv`, "text/csv;charset=utf-8")}><Download size={17} /> CSV affiché</button>
          <button className="button primary" onClick={exportExcel}><FileSpreadsheet size={17} /> Classeur Excel</button>
        </div>
      </div>

      {deleteSuccess && <div className="alert success"><ShieldCheck size={21} /><div><strong>Suppression terminée et sauvegardée</strong><span>{deleteSuccess}</span></div><button className="alert-close" onClick={() => setDeleteSuccess("")} aria-label="Fermer"><X size={17} /></button></div>}

      <div className="history-toolbar">
        <div className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Client ou note…" /></div>
        <select value={year} onChange={(event) => setYear(event.target.value === "all" ? "all" : Number(event.target.value))}><option value="all">Toutes les années</option>{years.map((item) => <option key={item}>{item}</option>)}</select>
        <select value={month} onChange={(event) => setMonth(event.target.value === "all" ? "all" : Number(event.target.value))}><option value="all">Tous les mois</option>{monthNames.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}</select>
        <div className="view-tabs">
          <button className={view === "summary" ? "active" : ""} onClick={() => setView("summary")}>Synthèse</button>
          <button className={view === "complete" ? "active" : ""} onClick={() => setView("complete")}>Rapport complet</button>
          <button className={view === "ledger" ? "active" : ""} onClick={() => setView("ledger")}>Ligne par ligne</button>
        </div>
      </div>

      {view === "summary" ? (
        <div className="table-card"><table><thead><tr><th className="selection-cell"><input type="checkbox" checked={allFilteredSelected} onChange={toggleAllFiltered} aria-label="Sélectionner toutes les journées affichées" /></th><th>Date</th><th>Taux LL/USD</th><th>Volume vendu</th><th>Stock fin</th><th>Ventes USD</th><th>Ventes LL</th><th>Dépenses USD</th><th>Dépenses LL</th><th>Résultat équiv.</th><th /></tr></thead><tbody>{filtered.map((day) => <tr key={day.recordDate} className={selectedDates.has(day.recordDate) ? "selected-row" : ""}><td className="selection-cell"><input type="checkbox" checked={selectedDates.has(day.recordDate)} onChange={() => toggleDate(day.recordDate)} aria-label={`Sélectionner la journée du ${formatDate(day.recordDate)}`} /></td><td><strong>{formatDate(day.recordDate)}</strong></td><td>{formatNumber(day.exchangeRate)}</td><td>{formatNumber(day.fuelVolumeSoldL)} L</td><td>{formatNumber(day.actualStockEndL)} L</td><td>{formatUsd(day.totals.totalSales.usd)}</td><td>{formatLbp(day.totals.totalSales.lbp)}</td><td>{formatUsd(day.totals.totalExpenses.usd)}</td><td>{formatLbp(day.totals.totalExpenses.lbp)}</td><td className={day.totals.netUsdEquivalent >= 0 ? "positive-text" : "negative-text"}><strong>{formatUsd(day.totals.netUsdEquivalent)}</strong></td><td><button className="icon-button" title="Modifier" onClick={() => onEdit(day.recordDate)}><Pencil size={16} /></button></td></tr>)}</tbody></table></div>
      ) : (
        <GenericTable rows={view === "complete" ? fullRows : journal} />
      )}

      {deleteDialogOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !deleting) setDeleteDialogOpen(false); }}>
          <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title">
            <div className="dialog-icon"><AlertTriangle size={25} /></div>
            <div className="dialog-title-row"><div><span className="eyebrow">ACTION SENSIBLE</span><h3 id="delete-dialog-title">Supprimer {selectedDates.size} journée{selectedDates.size > 1 ? "s" : ""} ?</h3></div><button className="icon-button" disabled={deleting} onClick={() => setDeleteDialogOpen(false)} aria-label="Fermer"><X size={18} /></button></div>
            <p>Les journées, leurs crédits et leurs remboursements seront retirés de l’application. Une sauvegarde SQLite complète sera créée automatiquement avant la suppression.</p>
            <div className="delete-date-list">{[...selectedDates].sort().map((date) => <span key={date}>{formatDate(date)}</span>)}</div>
            <label className="field"><span className="field-label">Tapez SUPPRIMER pour confirmer</span><input autoFocus value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value.toLocaleUpperCase("fr"))} placeholder="SUPPRIMER" /></label>
            {deleteError && <div className="alert error"><strong>Suppression impossible</strong><span>{deleteError}</span></div>}
            <div className="dialog-actions"><button className="button secondary" disabled={deleting} onClick={() => setDeleteDialogOpen(false)}>Annuler</button><button className="button destructive solid" disabled={deleting || deleteConfirmation !== "SUPPRIMER"} onClick={() => void confirmDeletion()}>{deleting ? <Loader2 className="spin" size={18} /> : <Trash2 size={18} />} Supprimer définitivement</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

function GenericTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <div className="empty-state"><h3>Aucune ligne pour ces filtres</h3></div>;
  const columns = Object.keys(rows[0]);
  return <div className="table-card wide-table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{column === "Date" ? formatDate(String(row[column])) : typeof row[column] === "number" ? formatNumber(Number(row[column]), 2) : String(row[column] ?? "")}</td>)}</tr>)}</tbody></table></div>;
}
