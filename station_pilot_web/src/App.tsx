import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Layout } from "./components/Layout";
import { api } from "./lib/api";
import { formatDate } from "./lib/format";
import type { CreditActionRequest, CustomerSummary, DailyRecord, Page } from "./types";

const OverviewPage = lazy(() => import("./pages/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const EntryPage = lazy(() => import("./pages/EntryPage").then((module) => ({ default: module.EntryPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const CreditsPage = lazy(() => import("./pages/CreditsPage").then((module) => ({ default: module.CreditsPage })));
const HistoryPage = lazy(() => import("./pages/HistoryPage").then((module) => ({ default: module.HistoryPage })));

const validPages: Page[] = ["overview", "entry", "dashboard", "credits", "history"];

function pageFromHash(): Page {
  const hash = window.location.hash.replace(/^#\/?/, "") as Page;
  return validPages.includes(hash) ? hash : "overview";
}

export default function App() {
  const [page, setPage] = useState<Page>(() => pageFromHash());
  const [days, setDays] = useState<DailyRecord[]>([]);
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [requestedEditDate, setRequestedEditDate] = useState<string>();
  const [requestedCreditAction, setRequestedCreditAction] = useState<CreditActionRequest>();

  const refresh = useCallback(async () => {
    try {
      setLoadError("");
      const [records, customerRecords] = await Promise.all([api.listDays(), api.listCustomers()]);
      setDays(records);
      setCustomers(customerRecords);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Connexion impossible avec l’API locale.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const syncPageWithHash = () => setPage(pageFromHash());
    if (!validPages.includes(window.location.hash.replace(/^#\/?/, "") as Page)) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#overview`);
    }
    window.addEventListener("hashchange", syncPageWithHash);
    return () => window.removeEventListener("hashchange", syncPageWithHash);
  }, []);

  const navigate = useCallback((nextPage: Page) => {
    setPage(nextPage);
    if (window.location.hash !== `#${nextPage}`) window.location.hash = nextPage;
  }, []);

  const navigateFromMenu = useCallback((nextPage: Page) => {
    setRequestedEditDate(undefined);
    setRequestedCreditAction(undefined);
    navigate(nextPage);
  }, [navigate]);

  const editDay = (date: string) => {
    setRequestedCreditAction(undefined);
    setRequestedEditDate(date);
    navigate("entry");
  };

  const openCreditAction = (customer: CustomerSummary, type: CreditActionRequest["type"]) => {
    setRequestedEditDate(undefined);
    setRequestedCreditAction({ key: Date.now(), customer, type });
    navigate("entry");
  };

  const openNewCredit = () => {
    setRequestedEditDate(undefined);
    setRequestedCreditAction(undefined);
    navigate("entry");
  };

  const latestDate = days.length
    ? formatDate([...days].sort((a, b) => b.recordDate.localeCompare(a.recordDate))[0].recordDate)
    : undefined;

  return (
    <Layout page={page} onPageChange={navigateFromMenu} latestDate={latestDate}>
      {loading ? (
        <div className="app-loading"><Loader2 className="spin" size={30} /><span>Ouverture de la base locale…</span></div>
      ) : loadError ? (
        <div className="fatal-error">
          <AlertTriangle size={38} />
          <h2>Impossible de joindre l’API locale</h2>
          <p>{loadError}</p>
          <button className="button primary" onClick={() => void refresh()}><RefreshCw size={17} /> Réessayer</button>
        </div>
      ) : (
        <Suspense fallback={<div className="app-loading"><Loader2 className="spin" size={30} /><span>Chargement de l’écran…</span></div>}>
          {page === "overview" ? (
            <OverviewPage days={days} customers={customers} onNavigate={navigateFromMenu} onEditDay={editDay} />
          ) : page === "entry" ? (
            <EntryPage days={days} customers={customers} requestedEditDate={requestedEditDate} requestedCreditAction={requestedCreditAction} onSaved={refresh} />
          ) : page === "dashboard" ? (
            <DashboardPage days={days} />
          ) : page === "credits" ? (
            <CreditsPage customers={customers} onAction={openCreditAction} onNew={openNewCredit} />
          ) : (
            <HistoryPage days={days} onEdit={editDay} onDeleted={refresh} />
          )}
        </Suspense>
      )}
    </Layout>
  );
}
