export const formatUsd = (value: number): string =>
  new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(value || 0);

export const formatLbp = (value: number): string =>
  `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(value || 0)} LL`;

export const formatNumber = (value: number, digits = 0): string =>
  new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value || 0);

export const formatDate = (isoDate: string): string => {
  if (!isoDate) return "—";
  return new Intl.DateTimeFormat("fr-FR").format(new Date(`${isoDate}T12:00:00`));
};

export const monthNames = [
  "Janvier",
  "Février",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Août",
  "Septembre",
  "Octobre",
  "Novembre",
  "Décembre",
];

export const isoWeek = (dateString: string): number => {
  const date = new Date(`${dateString}T12:00:00`);
  const target = new Date(date.valueOf());
  const day = (date.getDay() + 6) % 7;
  target.setDate(target.getDate() - day + 3);
  const firstThursday = new Date(target.getFullYear(), 0, 4);
  const firstDay = (firstThursday.getDay() + 6) % 7;
  firstThursday.setDate(firstThursday.getDate() - firstDay + 3);
  return 1 + Math.round((target.valueOf() - firstThursday.valueOf()) / 604_800_000);
};

export const csvEscape = (value: unknown): string => {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
