import { Route, Routes } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { HistoryPage } from "./pages/HistoryPage";
import { NewTestPage } from "./pages/NewTestPage";
import { RunPage } from "./pages/RunPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <div className="flex h-screen w-screen bg-base-950 text-slate-200">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<NewTestPage />} />
          <Route path="/run/:id" element={<RunPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
