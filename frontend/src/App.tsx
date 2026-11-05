import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import ThesisInput from "./pages/ThesisInput";
import PipelineStatus from "./pages/PipelineStatus";
import MemoView from "./pages/MemoView";
import ExceptionQueue from "./pages/ExceptionQueue";
import OutreachPanel from "./pages/OutreachPanel";

const NAV = [
  { to: "/", label: "Thesis", end: true },
  { to: "/pipeline", label: "Pipeline" },
  { to: "/memos", label: "Memos" },
  { to: "/exceptions", label: "Exceptions" },
  { to: "/outreach", label: "Outreach" },
];

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Crushdata</span>
        <nav>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ThesisInput />} />
          <Route path="/pipeline" element={<PipelineStatus />} />
          <Route path="/memos" element={<MemoView />} />
          <Route path="/exceptions" element={<ExceptionQueue />} />
          <Route path="/outreach" element={<OutreachPanel />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
