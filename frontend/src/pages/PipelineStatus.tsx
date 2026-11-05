import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getStatus } from "../api";
import { getJobId } from "../jobStore";
import type { JobStatus, PipelineStage } from "../types";

const STEPS: { stage: Exclude<PipelineStage, "done">; label: string; hint: string }[] = [
  { stage: "discovery", label: "Discovery", hint: "Finding companies that match the thesis" },
  { stage: "verification", label: "Verification", hint: "Verifying founder identity and background" },
  { stage: "signal_analysis", label: "Signal analysis", hint: "Headcount, hiring and funding signals" },
  { stage: "memo_generation", label: "Memo generation", hint: "Writing memos and outreach drafts" },
];

export default function PipelineStatus() {
  const jobId = getJobId();
  const navigate = useNavigate();
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll every 2 seconds. Redirect to results when done.
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const s = await getStatus(jobId);
        if (cancelled) return;
        setStatus(s);
        setError(null);
        if (s.status === "done") {
          navigate("/results");
          return;
        }
        if (s.status === "failed") return;
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Could not reach the backend.");
      }
      timer = window.setTimeout(tick, 2000);
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, navigate]);

  if (!jobId) {
    return (
      <section>
        <h1>Pipeline status</h1>
        <p className="muted">No run in progress yet.</p>
        <Link to="/" className="primary-link">
          Start a run
        </Link>
      </section>
    );
  }

  const progress = status?.progress;
  const currentIndex = progress ? STEPS.findIndex((s) => s.stage === progress.stage) : -1;
  const found = progress?.companies_found ?? 0;
  const processed = progress?.companies_processed ?? 0;
  const pct = found > 0 ? Math.round((processed / found) * 100) : 0;
  const failed = status?.status === "failed";

  return (
    <section>
      <h1>Pipeline status</h1>
      <p className="muted lead">
        Job <code>{jobId}</code> {failed ? "failed." : "is running. This page updates every 2 seconds."}
      </p>

      {error && (
        <p className="error" role="alert">
          Can't reach the backend ({error}). Retrying...
        </p>
      )}

      <ol className="steps">
        {STEPS.map((s, i) => {
          const state = failed && i === currentIndex ? "error" : i < currentIndex ? "done" : i === currentIndex ? "running" : "pending";
          return (
            <li key={s.stage} className={`step ${state}`}>
              <span className="dot" />
              <div className="step-text">
                <strong>{s.label}</strong>
                <span className="muted">{s.hint}</span>
              </div>
              {state === "running" && <span className="spinner" aria-label="In progress" />}
            </li>
          );
        })}
      </ol>

      <div className="progress-card">
        <div className="row">
          <strong>
            {processed} of {found} companies processed
          </strong>
          <span className="muted">{pct}%</span>
        </div>
        <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <div className="bar-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {failed && (
        <p className="error" role="alert">
          The run failed. <Link to="/">Go back and try again.</Link>
        </p>
      )}
    </section>
  );
}
