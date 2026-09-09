import { Routes, Route, useLocation } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { NavBar } from "./components/NavBar";
import { ScanPage } from "./pages/ScanPage";
import { InventoryPage } from "./pages/InventoryPage";
import { InventoryItemPage } from "./pages/InventoryItemPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { ExpiringSoonPage } from "./pages/ExpiringSoonPage";
import { DemoPage } from "./pages/DemoPage";
import { DemoItemPage } from "./pages/DemoItemPage";
import { listPendingReviews, listInventory } from "./lib/api";

export default function App() {
  const location = useLocation();
  // /demo must make zero calls to the live backend (it's meant to work
  // fully offline, for recording) — the nav badge polling below is
  // otherwise unconditional, so it has to be explicitly skipped here.
  const isDemoRoute = location.pathname.startsWith("/demo");

  const [pendingCount, setPendingCount] = useState(0);
  const [expiringCount, setExpiringCount] = useState(0);

  const refreshPendingCount = useCallback(() => {
    listPendingReviews()
      .then((items) => setPendingCount(items.length))
      .catch(() => {
        /* nav badge is best-effort; page-level fetches surface real errors */
      });
  }, []);

  const refreshExpiringCount = useCallback(() => {
    listInventory()
      .then((items) =>
        setExpiringCount(items.filter((i) => i.expiry_status === "expired" || i.expiry_status === "near_expiry").length)
      )
      .catch(() => {
        /* nav badge is best-effort; page-level fetches surface real errors */
      });
  }, []);

  useEffect(() => {
    if (isDemoRoute) return;
    refreshPendingCount();
    refreshExpiringCount();
    const id = window.setInterval(() => {
      refreshPendingCount();
      refreshExpiringCount();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [isDemoRoute, refreshPendingCount, refreshExpiringCount]);

  return (
    <div className="min-h-screen">
      {/* Same header for every route, /demo included — pendingCount/
          expiringCount simply stay at their initial 0 while isDemoRoute is
          true, since the effect above never fires to change them.
          demoMode swaps the nav tabs for a single "Exit demo" link. */}
      <NavBar pendingReviewCount={pendingCount} expiringCount={expiringCount} demoMode={isDemoRoute} />
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
        <Routes>
          <Route path="/" element={<ScanPage onScanComplete={refreshPendingCount} />} />
          <Route path="/inventory" element={<InventoryPage />} />
          <Route path="/inventory/:itemId" element={<InventoryItemPage />} />
          <Route path="/review" element={<ReviewQueuePage onQueueChange={refreshPendingCount} />} />
          <Route path="/expiring" element={<ExpiringSoonPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/demo/item/:itemId" element={<DemoItemPage />} />
        </Routes>
      </main>
    </div>
  );
}
