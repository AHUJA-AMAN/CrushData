import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startRun } from "../api";

export default function ThesisInput() {
  const [thesis, setThesis] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function run() {
    if (!thesis.trim()) return;
    setBusy(true);
    try {
      await startRun(thesis.trim());
      navigate("/pipeline");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Thesis</h1>
      <p className="muted">Describe who you want to find. The agent does the sourcing and diligence.</p>
      <textarea
        rows={5}
        placeholder="e.g. Seed-stage Indian dev-tools founders with prior infra experience"
        value={thesis}
        onChange={(e) => setThesis(e.target.value)}
      />
      <button className="primary" onClick={run} disabled={busy || !thesis.trim()}>
        {busy ? "Starting..." : "Run"}
      </button>
    </section>
  );
}
