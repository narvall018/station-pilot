import type { CalculatedTotals, DailyInput, MoneyPair } from "../types";

const add = (pairs: MoneyPair[]): MoneyPair =>
  pairs.reduce(
    (total, pair) => ({ usd: total.usd + pair.usd, lbp: total.lbp + pair.lbp }),
    { usd: 0, lbp: 0 },
  );

export const toUsd = (money: MoneyPair, rate: number): number =>
  money.usd + (rate > 0 ? money.lbp / rate : 0);

export function calculateTotals(day: DailyInput): CalculatedTotals {
  const creditSold = add(
    day.creditSales.map((entry) =>
      entry.currency === "USD"
        ? { usd: Number(entry.amount) || 0, lbp: 0 }
        : { usd: 0, lbp: Number(entry.amount) || 0 },
    ),
  );
  const creditCollected = add(
    day.creditPayments.map((entry) =>
      entry.currency === "USD"
        ? { usd: Number(entry.amount) || 0, lbp: 0 }
        : { usd: 0, lbp: Number(entry.amount) || 0 },
    ),
  );
  const totalSales = add([...Object.values(day.sales), creditSold]);
  const totalExpenses = add(Object.values(day.expenses));
  const net = {
    usd: totalSales.usd - totalExpenses.usd,
    lbp: totalSales.lbp - totalExpenses.lbp,
  };
  const cashTheoreticalEnd = {
    usd:
      day.cashOpening.usd +
      totalSales.usd -
      creditSold.usd +
      creditCollected.usd -
      totalExpenses.usd,
    lbp:
      day.cashOpening.lbp +
      totalSales.lbp -
      creditSold.lbp +
      creditCollected.lbp -
      totalExpenses.lbp,
  };
  const theoreticalStockEndL =
    day.openingStockL + day.fuelInputL - day.fuelVolumeSoldL;

  return {
    totalSales,
    totalExpenses,
    net,
    creditSold,
    creditCollected,
    salesUsdEquivalent: toUsd(totalSales, day.exchangeRate),
    expensesUsdEquivalent: toUsd(totalExpenses, day.exchangeRate),
    netUsdEquivalent: toUsd(net, day.exchangeRate),
    creditSoldUsdEquivalent: toUsd(creditSold, day.exchangeRate),
    creditCollectedUsdEquivalent: toUsd(creditCollected, day.exchangeRate),
    theoreticalStockEndL,
    stockVarianceL: day.actualStockEndL - theoreticalStockEndL,
    cashTheoreticalEnd,
    cashVariance: {
      usd: day.cashActualEnd.usd - cashTheoreticalEnd.usd,
      lbp: day.cashActualEnd.lbp - cashTheoreticalEnd.lbp,
    },
  };
}
