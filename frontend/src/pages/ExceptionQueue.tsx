import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getResults } from "../api";
import { DecisionBadge } from "../components/bits";
import { getJobId, getResolved, setResolved } from "../jobStore";
import type { CompanyResult } from "../types";

export default function ExceptionQueue() {
  const jobId = getJobId();
  const [items, setItems] = useState<CompanyResult[] | null>(null);
  const [resolved, setResolvedState] = useState<string[]>(() => (jobId ? getResolved(jobId) : []));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    getResults(jobId)
      .then((r) => setItems(r.results.filter((c) => c.exception_flag)))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load exceptions."));
  }, [jobId]);

  function toggle(domain: string) {
    if (!jobId) return;
    const next = resolved.includes(domain) ? resolved.filter((d) => d !== domain) : [...resolved, domain];
    setResolvedState(next);
    setResolved(jobId, next);
  }

  if (!jobId) {
    return (
      <section>
        <h1>Exception queue</h1>
        <p className="muted">No run yet.</p>
        <Link to="/" className="primary-link">
          Start a run
        </Link>
      </section>
    );
  }

  const open = (items ?? []).filter((c) => !resolved.includes(c.domain));
  const done = (items ?? []).filter((c) => resolved.includes(c.domain));

  return (
    <section>
      <h1>Exception queue</h1>
      <p className="muted lead">Companies the agent escalated because of conflicting data, unclear identity or thin signals.</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!items && !error && <p className="muted">Loading...</p>}
      {items && items.length === 0 && <p className="muted">No exceptions. Nothing needs your review.</p>}

      {open.length > 0 && (
        <div className="exceptions">
          {open.map((c) => (
            <article key={c.domain} className="exception">
              <div className="row">
                <h3>{c.company_name}</h3>
                <DecisionBadge decision={c.decision} />
              </div>
              <p className="reason">{c.exception_reason ?? "Flagged for human review."}</p>
              <div className="muted small">
                {c.location} · {c.stage}
              </div>
              <button type="button" className="primary small-btn" onClick={() => toggle(c.domain)}>
                Mark resolved
              </button>
            </article>
          ))}
        </div>
      )}

      {done.length > 0 && (
        <>
          <h4 className="resolved-title">Resolved ({done.length})</h4>
          <div className="exceptions">
            {done.map((c) => (
              <article key={c.domain} className="exception resolved">
                <div className="row">
                  <h3>{c.company_name}</h3>
                  <span className="ctag verified">Resolved</span>
                </div>
                <p className="reason">{c.exception_reason}</p>
                <button type="button" className="link" onClick={() => toggle(c.domain)}>
                  Reopen
                </button>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
