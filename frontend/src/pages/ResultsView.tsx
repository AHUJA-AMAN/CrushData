import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getResults } from "../api";
import { KillButton } from "../components/bits";
import ResultCard from "../components/ResultCard";
import { getJobId } from "../jobStore";
import type { CompanyResult, Decision, JobProgress, JobState } from "../types";

type Filter = "all" | Decision;
const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "meet", label: "Meet" },
  { value: "watch", label: "Watch" },
  { value: "pass", label: "Pass" },
];

export default function ResultsView() {
  const jobId = getJobId();
  const [results, setResults] = useState<CompanyResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [progress, setProgress] = useState<JobProgress | null>(null);

  // Memos land one by one: keep polling while the job is running, show each as soon as it arrives.
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    let timer: number | undefined;
    const tick = async () => {
      let again = true;
      try {
        const r = await getResults(jobId);
        if (stop) return;
        setResults(r.results ?? []);
        setJobState(r.status);
        setProgress(r.progress ?? null);
        setError(null);
        again = r.status === "running";
      } catch (e) {
        if (stop) return;
        setError(e instanceof Error ? e.message : "Could not load results.");
      }
      if (again) timer = window.setTimeout(tick, 2500);
    };
    tick();
    return () => {
      stop = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: 0, meet: 0, watch: 0, pass: 0 };
    for (const r of results ?? []) {
      c.all += 1;
      c[r.decision] += 1;
    }
    return c;
  }, [results]);

  if (!jobId) {
    return (
      <section>
        <h1>Results</h1>
        <p className="muted">No results yet.</p>
        <Link to="/" className="primary-link">
          Start a run
        </Link>
      </section>
    );
  }

  const shown = (results ?? []).filter((r) => filter === "all" || r.decision === filter);

  return (
    <section>
      <h1>Results</h1>
      <p className="muted lead">One memo per company, with every claim cited to its source.</p>

      {jobState === "running" && (
        <div className="progress-card live">
          <div className="row">
            <strong>
              <span className="spinner" aria-hidden="true" /> Preparing memos: {progress?.companies_processed ?? 0} of{" "}
              {progress?.companies_found ?? 0} done
            </strong>
            <KillButton jobId={jobId} onKilled={() => setJobState("cancelled")} />
          </div>
          <p className="muted small">Each memo shows up below as soon as it's ready.</p>
        </div>
      )}
      {jobState === "awaiting_selection" && (
        <p className="muted">
          Discovery is done. <Link to="/status">Pick the companies</Link> you want memos for.
        </p>
      )}
      {jobState === "cancelled" && <p className="muted">Run stopped. Memos prepared before the stop are below.</p>}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!results && !error && <p className="muted">Loading results...</p>}

      {results && (
        <>
          <div className="filterbar" role="tablist" aria-label="Filter by decision">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                role="tab"
                aria-selected={filter === f.value}
                className={`filter ${f.value}${filter === f.value ? " on" : ""}`}
                onClick={() => setFilter(f.value)}
              >
                {f.label} <span className="count">{counts[f.value]}</span>
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <p className="muted">{jobState === "running" ? "The first memo is on its way..." : "No companies match this filter."}</p>
          ) : (
            <div className="results">
              {shown.map((c) => (
                <ResultCard key={c.company_name} company={c} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
