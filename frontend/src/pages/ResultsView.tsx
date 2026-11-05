import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getResults } from "../api";
import ResultCard from "../components/ResultCard";
import { getJobId } from "../jobStore";
import type { CompanyResult, Decision } from "../types";

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

  useEffect(() => {
    if (!jobId) return;
    getResults(jobId)
      .then((r) => setResults(r.results))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load results."));
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
            <p className="muted">No companies match this filter.</p>
          ) : (
            <div className="results">
              {shown.map((c) => (
                <ResultCard key={c.domain} company={c} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
