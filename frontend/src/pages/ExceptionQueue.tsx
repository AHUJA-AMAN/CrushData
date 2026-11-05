import { useEffect, useState } from "react";
import { getExceptions } from "../api";
import type { ExceptionItem } from "../types";

const REASON_LABEL: Record<ExceptionItem["reason"], string> = {
  conflicting_data: "Conflicting data",
  ambiguous_identity: "Ambiguous identity",
  thin_signals: "Thin signals",
};

export default function ExceptionQueue() {
  const [items, setItems] = useState<ExceptionItem[]>([]);

  useEffect(() => {
    getExceptions("current").then(setItems);
  }, []);

  return (
    <section>
      <h1>Exception Queue</h1>
      <p className="muted">Companies escalated for human review. Placeholder view.</p>
      <div className="grid">
        {items.map((e) => (
          <article key={e.id} className="card">
            <div className="row">
              <h3>{e.company}</h3>
              <span className="badge watch">{REASON_LABEL[e.reason]}</span>
            </div>
            <p>{e.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
