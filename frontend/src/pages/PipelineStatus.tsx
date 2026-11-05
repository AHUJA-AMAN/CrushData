import { useEffect, useState } from "react";
import { getRun } from "../api";
import type { PipelineRun } from "../types";

export default function PipelineStatus() {
  const [run, setRun] = useState<PipelineRun | null>(null);

  useEffect(() => {
    getRun("current").then(setRun);
  }, []);

  return (
    <section>
      <h1>Pipeline Status</h1>
      <p className="muted">Live progress while the agent runs. Placeholder view.</p>
      {run && (
        <ol className="steps">
          {run.steps.map((s) => (
            <li key={s.id} className={`step ${s.status}`}>
              <span className="dot" />
              <span>{s.label}</span>
              {s.detail && <span className="muted">{s.detail}</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
