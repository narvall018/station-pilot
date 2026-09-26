export type Currency = "USD" | "LBP";
export type ViewMode = "day" | "week" | "month" | "year";
export type Page = "overview" | "entry" | "dashboard" | "credits" | "history";

export interface MoneyPair {
  usd: number;
  lbp: number;
}

export interface ClientTransaction {
  id?: number;
  customerId?: number;
  clientName: string;
  amount: number;
  currency: Currency;
  note: string;
}

export interface CustomerSummary {
  id: number;
  name: string;
  totalCredit: MoneyPair;
  totalPaid: MoneyPair;
  balance: MoneyPair;
  transactionCount: number;
  lastActivityDate: string;
}

export interface CreditLedgerEntry {
  id: number;
  customerId: number;
  recordDate: string;
  type: "credit" | "payment";
  amount: number;
  currency: Currency;
  note: string;
}

export interface CustomerLedger {
  customer: CustomerSummary;
  entries: CreditLedgerEntry[];
}

export interface CreditActionRequest {
  key: number;
  customer: CustomerSummary;
  type: "credit" | "payment";
}

export interface DailyInput {
  recordDate: string;
  exchangeRate: number;
  tankCapacityL: number;
  openingStockL: number;
  fuelInputL: number;
  fuelVolumeSoldL: number;
  actualStockEndL: number;
  fuelCostUsdPerL: number;
  stockValueUsd: number;
  sales: {
    fuel: MoneyPair;
    tires: MoneyPair;
    gas: MoneyPair;
    wash: MoneyPair;
    other: MoneyPair;
  };
  expenses: {
    fuelPurchase: MoneyPair;
    electricity: MoneyPair;
    salaries: MoneyPair;
    tiresPurchase: MoneyPair;
    deliveryTip: MoneyPair;
    maintenance: MoneyPair;
    other: MoneyPair;
  };
  creditSales: ClientTransaction[];
  creditPayments: ClientTransaction[];
  cashOpening: MoneyPair;
  cashActualEnd: MoneyPair;
  notes: string;
}

export interface CalculatedTotals {
  totalSales: MoneyPair;
  totalExpenses: MoneyPair;
  net: MoneyPair;
  creditSold: MoneyPair;
  creditCollected: MoneyPair;
  salesUsdEquivalent: number;
  expensesUsdEquivalent: number;
  netUsdEquivalent: number;
  creditSoldUsdEquivalent: number;
  creditCollectedUsdEquivalent: number;
  theoreticalStockEndL: number;
  stockVarianceL: number;
  cashTheoreticalEnd: MoneyPair;
  cashVariance: MoneyPair;
}

export interface DailyRecord extends DailyInput {
  id: number;
  totals: CalculatedTotals;
  createdAt: string;
  updatedAt: string;
}

export const emptyMoney = (): MoneyPair => ({ usd: 0, lbp: 0 });

export function localIsoDate(date = new Date()): string {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 10);
}

export function emptyDay(recordDate = localIsoDate()): DailyInput {
  return {
    recordDate,
    exchangeRate: 89_500,
    tankCapacityL: 0,
    openingStockL: 0,
    fuelInputL: 0,
    fuelVolumeSoldL: 0,
    actualStockEndL: 0,
    fuelCostUsdPerL: 0,
    stockValueUsd: 0,
    sales: {
      fuel: emptyMoney(),
      tires: emptyMoney(),
      gas: emptyMoney(),
      wash: emptyMoney(),
      other: emptyMoney(),
    },
    expenses: {
      fuelPurchase: emptyMoney(),
      electricity: emptyMoney(),
      salaries: emptyMoney(),
      tiresPurchase: emptyMoney(),
      deliveryTip: emptyMoney(),
      maintenance: emptyMoney(),
      other: emptyMoney(),
    },
    creditSales: [],
    creditPayments: [],
    cashOpening: emptyMoney(),
    cashActualEnd: emptyMoney(),
    notes: "",
  };
}

export const SALES_LABELS: Record<keyof DailyInput["sales"], string> = {
  fuel: "Essence",
  tires: "Pneus",
  gas: "Bouteilles de gaz",
  wash: "Lavage",
  other: "Autres ventes",
};

export const EXPENSE_LABELS: Record<keyof DailyInput["expenses"], string> = {
  fuelPurchase: "Achat d’essence",
  electricity: "Électricité / Générateur",
  salaries: "Salaires",
  tiresPurchase: "Achat de pneus",
  deliveryTip: "Pourboire livreur",
  maintenance: "Travaux / Maintenance",
  other: "Autres dépenses",
};
