import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { calculateTotals } from "../src/lib/calculations.js";
import { csvEscape } from "../src/lib/format.js";
import type {
  ClientTransaction,
  CreditLedgerEntry,
  CustomerLedger,
  CustomerSummary,
  DailyInput,
  DailyRecord,
  MoneyPair,
} from "../src/types.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const dataDirectory = path.resolve(here, "data");
fs.mkdirSync(dataDirectory, { recursive: true });

export const databasePath = process.env.STATION_DB_PATH || path.join(dataDirectory, "station.db");
const backupDirectory = path.dirname(databasePath);
fs.mkdirSync(backupDirectory, { recursive: true });
const db = new Database(databasePath);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");
db.pragma("busy_timeout = 15000");

const salesKeys = ["fuel", "tires", "gas", "wash", "other"] as const;
const expenseKeys = [
  "fuelPurchase",
  "electricity",
  "salaries",
  "tiresPurchase",
  "deliveryTip",
  "maintenance",
  "other",
] as const;

const columns = [
  "record_date",
  "exchange_rate",
  "tank_capacity_l",
  "opening_stock_l",
  "fuel_input_l",
  "fuel_volume_sold_l",
  "actual_stock_end_l",
  "fuel_cost_usd_per_l",
  "stock_value_usd",
  ...salesKeys.flatMap((key) => [`sales_${snake(key)}_usd`, `sales_${snake(key)}_lbp`]),
  ...expenseKeys.flatMap((key) => [
    `expenses_${snake(key)}_usd`,
    `expenses_${snake(key)}_lbp`,
  ]),
  "cash_opening_usd",
  "cash_opening_lbp",
  "cash_actual_end_usd",
  "cash_actual_end_lbp",
  "notes",
] as const;

function snake(value: string): string {
  return value.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function customerKey(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("fr");
}

export function initializeDatabase(): void {
  const numericColumns = columns
    .filter((column) => !["record_date", "notes"].includes(column))
    .map((column) => `"${column}" REAL NOT NULL DEFAULT 0`)
    .join(",\n");

  db.exec(`
    CREATE TABLE IF NOT EXISTS daily_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      record_date TEXT NOT NULL UNIQUE,
      ${numericColumns},
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS customers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      name_key TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS credit_sales (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      record_date TEXT NOT NULL,
      customer_id INTEGER,
      client_name TEXT NOT NULL,
      amount REAL NOT NULL DEFAULT 0,
      currency TEXT NOT NULL CHECK(currency IN ('USD', 'LBP')),
      note TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      FOREIGN KEY(record_date) REFERENCES daily_records(record_date) ON DELETE CASCADE,
      FOREIGN KEY(customer_id) REFERENCES customers(id)
    );

    CREATE TABLE IF NOT EXISTS credit_payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      record_date TEXT NOT NULL,
      customer_id INTEGER,
      client_name TEXT NOT NULL,
      amount REAL NOT NULL DEFAULT 0,
      currency TEXT NOT NULL CHECK(currency IN ('USD', 'LBP')),
      note TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      FOREIGN KEY(record_date) REFERENCES daily_records(record_date) ON DELETE CASCADE,
      FOREIGN KEY(customer_id) REFERENCES customers(id)
    );

    CREATE INDEX IF NOT EXISTS idx_credit_sales_date ON credit_sales(record_date);
    CREATE INDEX IF NOT EXISTS idx_credit_payments_date ON credit_payments(record_date);
  `);

  for (const table of ["credit_sales", "credit_payments"] as const) {
    const fields = db.pragma(`table_info(${table})`) as { name: string }[];
    if (!fields.some((field) => field.name === "customer_id")) {
      db.exec(`ALTER TABLE ${table} ADD COLUMN customer_id INTEGER REFERENCES customers(id)`);
    }
  }
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_credit_sales_customer ON credit_sales(customer_id);
    CREATE INDEX IF NOT EXISTS idx_credit_payments_customer ON credit_payments(customer_id);
  `);
  migrateCreditCustomers();
}

function upsertCustomer(name: string, requestedId?: number): { id: number; name: string } {
  if (requestedId) {
    const existing = db.prepare("SELECT id, name FROM customers WHERE id = ?").get(requestedId) as { id: number; name: string } | undefined;
    if (existing) return existing;
  }
  const cleanName = name.trim().replace(/\s+/g, " ");
  const key = customerKey(cleanName);
  const existing = db.prepare("SELECT id, name FROM customers WHERE name_key = ?").get(key) as { id: number; name: string } | undefined;
  if (existing) return existing;
  const now = new Date().toISOString();
  const result = db.prepare("INSERT INTO customers (name, name_key, created_at, updated_at) VALUES (?, ?, ?, ?)").run(cleanName, key, now, now);
  return { id: Number(result.lastInsertRowid), name: cleanName };
}

function migrateCreditCustomers(): void {
  db.transaction(() => {
    for (const table of ["credit_sales", "credit_payments"] as const) {
      const rows = db.prepare(`SELECT id, client_name FROM ${table} WHERE customer_id IS NULL`).all() as { id: number; client_name: string }[];
      const update = db.prepare(`UPDATE ${table} SET customer_id = ? WHERE id = ?`);
      rows.forEach((row) => {
        if (row.client_name.trim()) update.run(upsertCustomer(row.client_name).id, row.id);
      });
    }
  })();
}

function flatten(day: DailyInput): Record<string, string | number> {
  const row: Record<string, string | number> = {
    record_date: day.recordDate,
    exchange_rate: day.exchangeRate,
    tank_capacity_l: day.tankCapacityL,
    opening_stock_l: day.openingStockL,
    fuel_input_l: day.fuelInputL,
    fuel_volume_sold_l: day.fuelVolumeSoldL,
    actual_stock_end_l: day.actualStockEndL,
    fuel_cost_usd_per_l: day.fuelCostUsdPerL,
    stock_value_usd: day.stockValueUsd || day.actualStockEndL * day.fuelCostUsdPerL,
    cash_opening_usd: day.cashOpening.usd,
    cash_opening_lbp: day.cashOpening.lbp,
    cash_actual_end_usd: day.cashActualEnd.usd,
    cash_actual_end_lbp: day.cashActualEnd.lbp,
    notes: day.notes,
  };
  salesKeys.forEach((key) => {
    row[`sales_${snake(key)}_usd`] = day.sales[key].usd;
    row[`sales_${snake(key)}_lbp`] = day.sales[key].lbp;
  });
  expenseKeys.forEach((key) => {
    row[`expenses_${snake(key)}_usd`] = day.expenses[key].usd;
    row[`expenses_${snake(key)}_lbp`] = day.expenses[key].lbp;
  });
  return row;
}

function pair(row: Record<string, unknown>, prefix: string): MoneyPair {
  return {
    usd: Number(row[`${prefix}_usd`]) || 0,
    lbp: Number(row[`${prefix}_lbp`]) || 0,
  };
}

function getClientRows(table: "credit_sales" | "credit_payments", recordDate: string): ClientTransaction[] {
  return db
    .prepare(
      `SELECT id, customer_id AS customerId, client_name AS clientName, amount, currency, note
       FROM ${table} WHERE record_date = ? ORDER BY id`,
    )
    .all(recordDate) as ClientTransaction[];
}

function hydrate(row: Record<string, unknown>): DailyRecord {
  const input: DailyInput = {
    recordDate: String(row.record_date),
    exchangeRate: Number(row.exchange_rate) || 0,
    tankCapacityL: Number(row.tank_capacity_l) || 0,
    openingStockL: Number(row.opening_stock_l) || 0,
    fuelInputL: Number(row.fuel_input_l) || 0,
    fuelVolumeSoldL: Number(row.fuel_volume_sold_l) || 0,
    actualStockEndL: Number(row.actual_stock_end_l) || 0,
    fuelCostUsdPerL: Number(row.fuel_cost_usd_per_l) || 0,
    stockValueUsd: Number(row.stock_value_usd) || 0,
    sales: {
      fuel: pair(row, "sales_fuel"),
      tires: pair(row, "sales_tires"),
      gas: pair(row, "sales_gas"),
      wash: pair(row, "sales_wash"),
      other: pair(row, "sales_other"),
    },
    expenses: {
      fuelPurchase: pair(row, "expenses_fuel_purchase"),
      electricity: pair(row, "expenses_electricity"),
      salaries: pair(row, "expenses_salaries"),
      tiresPurchase: pair(row, "expenses_tires_purchase"),
      deliveryTip: pair(row, "expenses_delivery_tip"),
      maintenance: pair(row, "expenses_maintenance"),
      other: pair(row, "expenses_other"),
    },
    creditSales: getClientRows("credit_sales", String(row.record_date)),
    creditPayments: getClientRows("credit_payments", String(row.record_date)),
    cashOpening: pair(row, "cash_opening"),
    cashActualEnd: pair(row, "cash_actual_end"),
    notes: String(row.notes || ""),
  };
  return {
    ...input,
    id: Number(row.id),
    totals: calculateTotals(input),
    createdAt: String(row.created_at),
    updatedAt: String(row.updated_at),
  };
}

export function listDays(): DailyRecord[] {
  return (db.prepare("SELECT * FROM daily_records ORDER BY record_date").all() as Record<
    string,
    unknown
  >[]).map(hydrate);
}

export function getDay(recordDate: string): DailyRecord | null {
  const row = db
    .prepare("SELECT * FROM daily_records WHERE record_date = ?")
    .get(recordDate) as Record<string, unknown> | undefined;
  return row ? hydrate(row) : null;
}

function insertClients(
  table: "credit_sales" | "credit_payments",
  recordDate: string,
  entries: ClientTransaction[],
  now: string,
): void {
  const statement = db.prepare(
    `INSERT INTO ${table} (record_date, customer_id, client_name, amount, currency, note, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  );
  entries.forEach((entry) => {
    if (entry.clientName.trim() && entry.amount > 0) {
      const customer = upsertCustomer(entry.clientName, entry.customerId);
      statement.run(
        recordDate,
        customer.id,
        customer.name,
        entry.amount,
        entry.currency,
        entry.note.trim(),
        now,
      );
    }
  });
}

export function saveDay(day: DailyInput, allowUpdate: boolean): DailyRecord {
  const existing = getDay(day.recordDate);
  if (existing && !allowUpdate) {
    throw new Error("Une journée existe déjà à cette date. Utilisez le mode modification.");
  }
  const values = flatten(day);
  const now = new Date().toISOString();

  db.transaction(() => {
    if (existing) {
      const editableColumns = columns.filter((column) => column !== "record_date");
      db.prepare(
        `UPDATE daily_records SET ${editableColumns
          .map((column) => `"${column}" = @${column}`)
          .join(", ")}, updated_at = @updated_at WHERE record_date = @record_date`,
      ).run({ ...values, updated_at: now });
      db.prepare("DELETE FROM credit_sales WHERE record_date = ?").run(day.recordDate);
      db.prepare("DELETE FROM credit_payments WHERE record_date = ?").run(day.recordDate);
    } else {
      const insertColumns = [...columns, "created_at", "updated_at"];
      db.prepare(
        `INSERT INTO daily_records (${insertColumns.map((column) => `"${column}"`).join(", ")})
         VALUES (${insertColumns.map((column) => `@${column}`).join(", ")})`,
      ).run({ ...values, created_at: now, updated_at: now });
    }
    insertClients("credit_sales", day.recordDate, day.creditSales, now);
    insertClients("credit_payments", day.recordDate, day.creditPayments, now);
  })();

  syncCsvBackups();
  return getDay(day.recordDate)!;
}

export async function deleteDays(recordDates: string[]): Promise<{ deletedDates: string[]; backupName: string }> {
  const requested = [...new Set(recordDates)];
  if (!requested.length) return { deletedDates: [], backupName: "" };

  const placeholders = requested.map(() => "?").join(", ");
  const existing = (db.prepare(`SELECT record_date FROM daily_records WHERE record_date IN (${placeholders}) ORDER BY record_date`).all(...requested) as { record_date: string }[])
    .map((row) => row.record_date);
  if (!existing.length) return { deletedDates: [], backupName: "" };

  const backupsDirectory = path.join(backupDirectory, "backups");
  fs.mkdirSync(backupsDirectory, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupName = `station_before_delete_${timestamp}.db`;
  await db.backup(path.join(backupsDirectory, backupName));

  const deletePlaceholders = existing.map(() => "?").join(", ");
  db.transaction(() => {
    db.prepare(`DELETE FROM daily_records WHERE record_date IN (${deletePlaceholders})`).run(...existing);
    db.prepare(`
      DELETE FROM customers
      WHERE id NOT IN (
        SELECT customer_id FROM credit_sales WHERE customer_id IS NOT NULL
        UNION
        SELECT customer_id FROM credit_payments WHERE customer_id IS NOT NULL
      )
    `).run();
  })();

  syncCsvBackups();
  return { deletedDates: existing, backupName };
}

function customerLedgerEntries(customerId: number): CreditLedgerEntry[] {
  return db.prepare(`
    SELECT id, customer_id AS customerId, record_date AS recordDate, 'credit' AS type, amount, currency, note
    FROM credit_sales WHERE customer_id = ?
    UNION ALL
    SELECT id, customer_id AS customerId, record_date AS recordDate, 'payment' AS type, amount, currency, note
    FROM credit_payments WHERE customer_id = ?
    ORDER BY recordDate, type, id
  `).all(customerId, customerId) as CreditLedgerEntry[];
}

function summarizeCustomer(customer: { id: number; name: string }): CustomerSummary {
  const entries = customerLedgerEntries(customer.id);
  const totalCredit: MoneyPair = { usd: 0, lbp: 0 };
  const totalPaid: MoneyPair = { usd: 0, lbp: 0 };
  entries.forEach((entry) => {
    const target = entry.type === "credit" ? totalCredit : totalPaid;
    if (entry.currency === "USD") target.usd += entry.amount;
    else target.lbp += entry.amount;
  });
  return {
    id: customer.id,
    name: customer.name,
    totalCredit,
    totalPaid,
    balance: { usd: totalCredit.usd - totalPaid.usd, lbp: totalCredit.lbp - totalPaid.lbp },
    transactionCount: entries.length,
    lastActivityDate: entries.at(-1)?.recordDate || "",
  };
}

export function listCustomers(): CustomerSummary[] {
  return (db.prepare("SELECT id, name FROM customers ORDER BY name COLLATE NOCASE").all() as { id: number; name: string }[])
    .map(summarizeCustomer);
}

export function getCustomerLedger(customerId: number): CustomerLedger | null {
  const customer = db.prepare("SELECT id, name FROM customers WHERE id = ?").get(customerId) as { id: number; name: string } | undefined;
  if (!customer) return null;
  return { customer: summarizeCustomer(customer), entries: customerLedgerEntries(customer.id) };
}

function writeCsv(fileName: string, rows: Record<string, unknown>[], emptyHeaders: string[]): void {
  const headers = rows.length ? Object.keys(rows[0]) : emptyHeaders;
  const content = [
    headers.map(csvEscape).join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(",")),
  ].join("\n");
  const temporary = path.join(backupDirectory, `${fileName}.tmp`);
  fs.writeFileSync(temporary, `\uFEFF${content}\n`, "utf8");
  fs.renameSync(temporary, path.join(backupDirectory, fileName));
}

export function syncCsvBackups(): void {
  const dailyHeaders = [
    "date", "taux_usd_lbp", "capacite_reservoir_l", "stock_ouverture_l",
    "entrees_carburant_l", "ventes_essence_l", "stock_theorique_fin_l",
    "stock_reel_fin_l", "ecart_stock_l", "cout_carburant_usd_l", "valeur_stock_usd",
    ...salesKeys.flatMap((key) => [`vente_${snake(key)}_usd`, `vente_${snake(key)}_lbp`]),
    ...expenseKeys.flatMap((key) => [`depense_${snake(key)}_usd`, `depense_${snake(key)}_lbp`]),
    "credit_vendu_usd", "credit_vendu_lbp", "credit_encaisse_usd", "credit_encaisse_lbp",
    "total_ventes_usd", "total_ventes_lbp", "total_depenses_usd", "total_depenses_lbp",
    "ventes_equiv_usd", "depenses_equiv_usd", "resultat_equiv_usd",
    "caisse_ouverture_usd", "caisse_theorique_usd", "caisse_reelle_usd", "ecart_caisse_usd",
    "caisse_ouverture_lbp", "caisse_theorique_lbp", "caisse_reelle_lbp", "ecart_caisse_lbp",
    "notes",
  ];
  const days = listDays().map((day) => {
    const row: Record<string, unknown> = {
      date: day.recordDate,
      taux_usd_lbp: day.exchangeRate,
      capacite_reservoir_l: day.tankCapacityL,
      stock_ouverture_l: day.openingStockL,
      entrees_carburant_l: day.fuelInputL,
      ventes_essence_l: day.fuelVolumeSoldL,
      stock_theorique_fin_l: day.totals.theoreticalStockEndL,
      stock_reel_fin_l: day.actualStockEndL,
      ecart_stock_l: day.totals.stockVarianceL,
      cout_carburant_usd_l: day.fuelCostUsdPerL,
      valeur_stock_usd: day.stockValueUsd,
    };
    salesKeys.forEach((key) => {
      row[`vente_${snake(key)}_usd`] = day.sales[key].usd;
      row[`vente_${snake(key)}_lbp`] = day.sales[key].lbp;
    });
    expenseKeys.forEach((key) => {
      row[`depense_${snake(key)}_usd`] = day.expenses[key].usd;
      row[`depense_${snake(key)}_lbp`] = day.expenses[key].lbp;
    });
    Object.assign(row, {
      credit_vendu_usd: day.totals.creditSold.usd,
      credit_vendu_lbp: day.totals.creditSold.lbp,
      credit_encaisse_usd: day.totals.creditCollected.usd,
      credit_encaisse_lbp: day.totals.creditCollected.lbp,
      total_ventes_usd: day.totals.totalSales.usd,
      total_ventes_lbp: day.totals.totalSales.lbp,
      total_depenses_usd: day.totals.totalExpenses.usd,
      total_depenses_lbp: day.totals.totalExpenses.lbp,
      ventes_equiv_usd: day.totals.salesUsdEquivalent,
      depenses_equiv_usd: day.totals.expensesUsdEquivalent,
      resultat_equiv_usd: day.totals.netUsdEquivalent,
      caisse_ouverture_usd: day.cashOpening.usd,
      caisse_theorique_usd: day.totals.cashTheoreticalEnd.usd,
      caisse_reelle_usd: day.cashActualEnd.usd,
      ecart_caisse_usd: day.totals.cashVariance.usd,
      caisse_ouverture_lbp: day.cashOpening.lbp,
      caisse_theorique_lbp: day.totals.cashTheoreticalEnd.lbp,
      caisse_reelle_lbp: day.cashActualEnd.lbp,
      ecart_caisse_lbp: day.totals.cashVariance.lbp,
      notes: day.notes,
    });
    return row;
  });
  const creditRows = db
    .prepare("SELECT * FROM credit_sales ORDER BY record_date, id")
    .all() as Record<string, unknown>[];
  const paymentRows = db
    .prepare("SELECT * FROM credit_payments ORDER BY record_date, id")
    .all() as Record<string, unknown>[];
  const clientHeaders = ["id", "record_date", "customer_id", "client_name", "amount", "currency", "note", "created_at"];
  writeCsv("station_data.csv", days, dailyHeaders);
  writeCsv("station_credits.csv", creditRows, clientHeaders);
  writeCsv("station_credit_payments.csv", paymentRows, clientHeaders);
}

initializeDatabase();
syncCsvBackups();
