import { Routes, Route } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { NavBar } from "./components/NavBar";
import { ScanPage } from "./pages/ScanPage";
import { InventoryPage } from "./pages/InventoryPage";
import { InventoryItemPage } from "./pages/InventoryItemPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { listPendingReviews } from "./lib/api";

export default function App() {
  const [pendingCount, setPendingCount] = useState(0);

  const refreshPendingCount = useCallback(() => {
    listPendingReviews()
      .then((items) => setPendingCount(items.length))
      .catch(() => {
        /* nav badge is best-effort; page-level fetches surface real errors */
      });
  }, []);

  useEffect(() => {
    refreshPendingCount();
    const id = window.setInterval(refreshPendingCount, 30_000);
    return () => window.clearInterval(id);
  }, [refreshPendingCount]);

  return (
    <div className="min-h-screen">
      <NavBar pendingReviewCount={pendingCount} />
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
        <Routes>
          <Route path="/" element={<ScanPage onScanComplete={refreshPendingCount} />} />
          <Route path="/inventory" element={<InventoryPage />} />
          <Route path="/inventory/:itemId" element={<InventoryItemPage />} />
          <Route path="/review" element={<ReviewQueuePage onQueueChange={refreshPendingCount} />} />
        </Routes>
      </main>
    </div>
  );
}
