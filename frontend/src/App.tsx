import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import ThesisInput from "./pages/ThesisInput";
import PipelineStatus from "./pages/PipelineStatus";
import ResultsView from "./pages/ResultsView";
import ExceptionQueue from "./pages/ExceptionQueue";

const NAV = [
  { to: "/", label: "Thesis", end: true },
  { to: "/status", label: "Pipeline" },
  { to: "/results", label: "Results" },
  { to: "/exceptions", label: "Exceptions" },
];

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <span className="brand-mark">C</span>
          CrushData
        </span>
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
          <Route path="/status" element={<PipelineStatus />} />
          <Route path="/results" element={<ResultsView />} />
          <Route path="/exceptions" element={<ExceptionQueue />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
