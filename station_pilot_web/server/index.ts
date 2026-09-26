import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import {
  databasePath,
  deleteDays,
  getCustomerLedger,
  getDay,
  listCustomers,
  listDays,
  saveDay,
} from "./database.js";

const moneySchema = z.object({
  usd: z.coerce.number().min(0),
  lbp: z.coerce.number().min(0),
});
const clientSchema = z.object({
  id: z.number().optional(),
  customerId: z.coerce.number().int().positive().optional(),
  clientName: z.string().trim().min(1),
  amount: z.coerce.number().positive(),
  currency: z.enum(["USD", "LBP"]),
  note: z.string().default(""),
});
const daySchema = z.object({
  recordDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  exchangeRate: z.coerce.number().positive(),
  tankCapacityL: z.coerce.number().min(0),
  openingStockL: z.coerce.number().min(0),
  fuelInputL: z.coerce.number().min(0),
  fuelVolumeSoldL: z.coerce.number().min(0),
  actualStockEndL: z.coerce.number().min(0),
  fuelCostUsdPerL: z.coerce.number().min(0),
  stockValueUsd: z.coerce.number().min(0),
  sales: z.object({
    fuel: moneySchema,
    tires: moneySchema,
    gas: moneySchema,
    wash: moneySchema,
    other: moneySchema,
  }),
  expenses: z.object({
    fuelPurchase: moneySchema,
    electricity: moneySchema,
    salaries: moneySchema,
    tiresPurchase: moneySchema,
    deliveryTip: moneySchema,
    maintenance: moneySchema,
    other: moneySchema,
  }),
  creditSales: z.array(clientSchema),
  creditPayments: z.array(clientSchema),
  cashOpening: moneySchema,
  cashActualEnd: moneySchema,
  notes: z.string(),
});
const deleteDaysSchema = z.object({
  dates: z.array(z.string().regex(/^\d{4}-\d{2}-\d{2}$/)).min(1).max(3660),
  confirmation: z.literal("SUPPRIMER"),
});

const app = express();
const port = Number(process.env.PORT || 4174);
const host = process.env.HOST || "127.0.0.1";
app.use(express.json({ limit: "1mb" }));

app.get("/api/health", (_request, response) => {
  response.json({ ok: true, database: path.basename(databasePath) });
});

app.get("/api/days", (_request, response) => {
  response.json(listDays());
});

app.get("/api/customers", (_request, response) => {
  response.json(listCustomers());
});

app.get("/api/customers/:id/ledger", (request, response) => {
  const customerId = Number(request.params.id);
  if (!Number.isInteger(customerId) || customerId <= 0) {
    return response.status(400).json({ error: "Identifiant client invalide." });
  }
  const ledger = getCustomerLedger(customerId);
  if (!ledger) return response.status(404).json({ error: "Client introuvable." });
  return response.json(ledger);
});

app.post("/api/days/delete-many", async (request, response) => {
  try {
    const payload = deleteDaysSchema.parse(request.body);
    const result = await deleteDays(payload.dates);
    return response.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Suppression impossible.";
    return response.status(400).json({ error: message });
  }
});

app.get("/api/days/:date", (request, response) => {
  const day = getDay(request.params.date);
  if (!day) return response.status(404).json({ error: "Journée introuvable." });
  return response.json(day);
});

app.post("/api/days", (request, response) => {
  try {
    const day = daySchema.parse(request.body);
    response.status(201).json(saveDay(day, false));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Données invalides.";
    response.status(400).json({ error: message });
  }
});

app.put("/api/days/:date", (request, response) => {
  try {
    const day = daySchema.parse({ ...request.body, recordDate: request.params.date });
    if (!getDay(request.params.date)) {
      return response.status(404).json({ error: "Journée introuvable." });
    }
    return response.json(saveDay(day, true));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Données invalides.";
    return response.status(400).json({ error: message });
  }
});

if (process.env.NODE_ENV === "production") {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const dist = path.resolve(here, "../dist");
  app.use(express.static(dist));
  app.get("*", (_request, response) => response.sendFile(path.join(dist, "index.html")));
}

app.listen(port, host, () => {
  console.log(`Station Pilot API : http://${host}:${port}`);
  console.log(`Base locale : ${databasePath}`);
});
