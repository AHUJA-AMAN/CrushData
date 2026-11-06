import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getResults, getStatus, selectCompanies } from "../api";
import { KillButton } from "../components/bits";
import { getJobId } from "../jobStore";
import type { Candidate, JobStatus, PipelineStage } from "../types";

const STEPS: { stage: PipelineStage; label: string; hint: string }[] = [
  { stage: "discovery", label: "Discovery", hint: "Finding founders that match the thesis" },
  { stage: "verification", label: "Verification", hint: "Verifying founder identity and background" },
  { stage: "selection", label: "Your pick", hint: "Choose which companies get a memo" },
  { stage: "memo_generation", label: "Memo generation", hint: "Signals, memos, decisions and outreach drafts" },
];

function CandidatePicker({ jobId, candidates }: { jobId: string; candidates: Candidate[] }) {
  const navigate = useNavigate();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string) =>
    setPicked((p) => {
      const next = new Set(p);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await selectCompanies(jobId, [...picked]);
      navigate("/results");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start memos.");
      setBusy(false);
    }
  }

  return (
    <div className="picker">
      <div className="row picker-head">
        <strong>
          {candidates.length} companies found. Pick the ones to write memos for.
        </strong>
        <span className="picker-tools">
          <button type="button" className="link" onClick={() => setPicked(new Set(candidates.map((c) => c.id)))}>
            Select all
          </button>
          <button type="button" className="link" onClick={() => setPicked(new Set())} disabled={picked.size === 0}>
            Clear
          </button>
        </span>
      </div>

      <ul className="candidates">
        {candidates.map((c) => (
          <li key={c.id}>
            <label className={`candidate${picked.has(c.id) ? " on" : ""}`}>
              <input type="checkbox" checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
              <div className="candidate-body">
                <div className="row">
                  <strong>{c.company_name}</strong>
                  <span className="muted small">{c.domain}</span>
                </div>
                <div className="meta">
                  {c.location && <span>{c.location}</span>}
                  {c.founded && <span>Founded {c.founded}</span>}
                  {c.headcount != null && <span>{c.headcount} people</span>}
                  <span>Funding {c.total_funding ?? "unknown"}</span>
                </div>
                {c.description && <p className="muted small">{c.description}</p>}
                <div className="muted small">
                  {c.founders.map((f) => `${f.name}${f.current_title ? ` (${f.current_title})` : ""}`).join(", ")}
                </div>
              </div>
            </label>
          </li>
        ))}
      </ul>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="actions sticky-actions">
        <button type="button" className="primary" disabled={picked.size === 0 || busy} onClick={start}>
          {busy ? "Starting..." : `Prepare ${picked.size} memo${picked.size === 1 ? "" : "s"}`}
        </button>
      </div>
    </div>
  );
}

export default function PipelineStatus() {
  const jobId = getJobId();
  const navigate = useNavigate();
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll every 2 seconds until discovery finishes (or the job ends).
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
        if (s.status === "awaiting_selection") {
          const r = await getResults(jobId);
          if (!cancelled) setCandidates(r.candidates ?? []);
          return;
        }
        if (s.status === "running" && s.progress.stage === "memo_generation") {
          navigate("/results");
          return;
        }
        if (s.status === "done") {
          navigate("/results");
          return;
        }
        if (s.status === "failed" || s.status === "cancelled") return;
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
  const failed = status?.status === "failed";
  const stopped = status?.status === "cancelled";
  const live = status?.status === "running" || status?.status === "awaiting_selection";

  return (
    <section>
      <div className="row">
        <h1>Pipeline status</h1>
        {live && (
          <KillButton
            jobId={jobId}
            onKilled={() => setStatus((s) => (s ? { ...s, status: "cancelled" } : s))}
          />
        )}
      </div>
      <p className="muted lead">
        Job <code>{jobId}</code>{" "}
        {failed
          ? "failed."
          : stopped
            ? "was stopped."
            : status?.status === "awaiting_selection"
              ? "found companies and is waiting for your pick."
              : "is running. This page updates every 2 seconds."}
      </p>

      {error && (
        <p className="error" role="alert">
          Can't reach the backend ({error}). Retrying...
        </p>
      )}

      <ol className="steps">
        {STEPS.map((s, i) => {
          const state =
            (failed || stopped) && i === currentIndex
              ? "error"
              : i < currentIndex
                ? "done"
                : i === currentIndex
                  ? "running"
                  : "pending";
          return (
            <li key={s.stage} className={`step ${state}`}>
              <span className="dot" />
              <div className="step-text">
                <strong>{s.label}</strong>
                <span className="muted">{s.hint}</span>
              </div>
              {state === "running" && s.stage !== "selection" && <span className="spinner" aria-label="In progress" />}
            </li>
          );
        })}
      </ol>

      {status?.status === "awaiting_selection" && candidates && (
        candidates.length ? (
          <CandidatePicker jobId={jobId} candidates={candidates} />
        ) : (
          <p className="muted">No companies matched. <Link to="/">Try a broader thesis.</Link></p>
        )
      )}

      {failed && (
        <p className="error" role="alert">
          The run failed{status?.error ? `: ${status.error}` : ""}. <Link to="/">Go back and try again.</Link>
        </p>
      )}
      {stopped && (
        <p className="muted">
          Stopped. <Link to="/results">See memos prepared so far</Link> or <Link to="/">start a new run</Link>.
        </p>
      )}
    </section>
  );
}
