import type { CustomerLedger, CustomerSummary, DailyInput, DailyRecord } from "../types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || "Une erreur inattendue est survenue.");
  }
  return body as T;
}

export const api = {
  listDays: () => request<DailyRecord[]>("/api/days"),
  getDay: (date: string) => request<DailyRecord>(`/api/days/${date}`),
  listCustomers: () => request<CustomerSummary[]>("/api/customers"),
  getCustomerLedger: (customerId: number) => request<CustomerLedger>(`/api/customers/${customerId}/ledger`),
  createDay: (day: DailyInput) =>
    request<DailyRecord>("/api/days", { method: "POST", body: JSON.stringify(day) }),
  updateDay: (date: string, day: DailyInput) =>
    request<DailyRecord>(`/api/days/${date}`, {
      method: "PUT",
      body: JSON.stringify(day),
    }),
  deleteDays: (dates: string[]) =>
    request<{ deletedDates: string[]; backupName: string }>("/api/days/delete-many", {
      method: "POST",
      body: JSON.stringify({ dates, confirmation: "SUPPRIMER" }),
    }),
};
