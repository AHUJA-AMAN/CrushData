import { useState } from "react";
import type { CompanyResult } from "../types";
import { ConfidenceTag, DecisionBadge, RichText } from "./bits";

function Founders({ company }: { company: CompanyResult }) {
  return (
    <div className="block">
      <h4>Founders</h4>
      <ul className="founders">
        {company.founders.map((f, i) => (
          <li key={`${f.name}-${i}`} className="founder">
            <div className="row">
              <strong>{f.name}</strong>
              {f.part_time_flag && <span className="flag">Possible part-time founder</span>}
            </div>
            <div className="muted">{f.current_title}</div>
            <div className="muted">{f.education}</div>
            {f.email_status !== undefined && (
              <div className="founder-email">
                {f.business_email ? (
                  <>
                    <code>{f.business_email}</code>
                    {f.email_status && <span className="muted small"> {f.email_status}</span>}
                  </>
                ) : (
                  <span className="muted small">Business email: {f.email_status ?? "not found"}</span>
                )}
              </div>
            )}
            {f.past_companies.length > 0 && (
              <div className="pills">
                {f.past_companies.map((c) => (
                  <span key={c} className="pill">
                    {c}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SignalsBar({ company }: { company: CompanyResult }) {
  const s = company.signals;
  const growth = s.headcount_growth_rate ?? "unknown";
  const negative = growth.trim().startsWith("-");
  return (
    <div className="signals" aria-label="Signals">
      <div className="signal">
        <span className="signal-label">Headcount</span>
        <span className="signal-value">
          {s.headcount_6m_ago ?? "?"} → {s.headcount_now ?? "?"}
        </span>
      </div>
      <div className="signal">
        <span className="signal-label">Growth (6 mo)</span>
        <span className={`signal-value ${negative ? "neg" : "pos"}`}>{growth}</span>
      </div>
      <div className="signal">
        <span className="signal-label">Open roles</span>
        <span className="signal-value">{s.recent_job_postings ?? "?"}</span>
      </div>
      <div className="signal wide">
        <span className="signal-label">Hiring in</span>
        {s.hiring_departments.length ? (
          <span className="pills">
            {s.hiring_departments.map((d) => (
              <span key={d} className="pill">
                {d}
              </span>
            ))}
          </span>
        ) : (
          <span className="muted">Not hiring</span>
        )}
      </div>
    </div>
  );
}

function CompetitorTable({ company }: { company: CompanyResult }) {
  const rows = company.memo_sections.competitive_landscape;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Company</th>
            <th>Founded</th>
            <th>Focus</th>
            <th>Target market</th>
            <th>Key clients</th>
            <th>Funding</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.company} className={r.company === company.company_name ? "self" : ""}>
              <td>{r.company}</td>
              <td>{r.founded}</td>
              <td>{r.focus}</td>
              <td>{r.target_market}</td>
              <td>{r.key_clients}</td>
              <td>{r.funding}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CitationsPanel({ company }: { company: CompanyResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="block">
      <button type="button" className="disclosure" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={`chevron${open ? " up" : ""}`} aria-hidden="true" />
        Citations <span className="count on">{company.citations.length}</span>
      </button>
      {open && (
        <ul className="citations">
          {company.citations.map((c, i) => (
            <li key={i}>
              <div className="cite-claim">{c.claim}</div>
              <div className="cite-meta">
                <span className="muted">{c.source}</span>
                <ConfidenceTag level={c.confidence} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Outreach({ email }: { email: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(email);
    } catch {
      // Fallback for browsers or contexts without clipboard permission
      const ta = document.createElement("textarea");
      ta.value = email;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="block outreach">
      <div className="row">
        <h4>Outreach email</h4>
        <button type="button" className="copy" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="email">{email}</pre>
    </div>
  );
}

export default function ResultCard({ company }: { company: CompanyResult }) {
  const [open, setOpen] = useState(true);
  const m = company.memo_sections;

  return (
    <article className={`result ${company.decision}`}>
      <header className="result-head">
        <div>
          <h2>{company.company_name}</h2>
          <div className="meta">
            <span>{company.location}</span>
            <span>Stage: {company.stage}</span>
            {company.founded && <span>Founded {company.founded}</span>}
            <span>Funding {company.total_funding ?? "unknown"}</span>
            <span>{company.domain}</span>
          </div>
        </div>
        <div className="head-right">
          <DecisionBadge decision={company.decision} />
          <span className="muted small">{company.confidence} confidence</span>
        </div>
      </header>

      {company.exception_flag && (
        <div className="exception-note" role="note">
          <strong>Needs review:</strong> {company.exception_reason ?? "Flagged for human review."}
        </div>
      )}

      <SignalsBar company={company} />
      <Founders company={company} />

      <button type="button" className="disclosure" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={`chevron${open ? " up" : ""}`} aria-hidden="true" />
        Memo
      </button>

      {open && (
        <div className="memo">
          <section>
            <h4>Summary</h4>
            <RichText text={m.summary} />
          </section>
          <section>
            <h4>Problem</h4>
            <RichText text={m.problem} />
          </section>
          <section>
            <h4>Market</h4>
            <RichText text={m.market} />
          </section>
          <section>
            <h4>Product</h4>
            <ul className="bullets">
              {m.product.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </section>
          <section>
            <h4>Competitive landscape</h4>
            <CompetitorTable company={company} />
          </section>
          <section className="xfactor">
            <h4>X factor</h4>
            <RichText text={m.x_factor} />
          </section>
        </div>
      )}

      <CitationsPanel company={company} />
      {company.decision === "meet" && company.outreach_email && <Outreach email={company.outreach_email} />}
    </article>
  );
}
