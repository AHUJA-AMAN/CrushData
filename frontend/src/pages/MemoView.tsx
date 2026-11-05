import { useEffect, useState } from "react";
import { getMemos } from "../api";
import type { Memo } from "../types";

export default function MemoView() {
  const [memos, setMemos] = useState<Memo[]>([]);

  useEffect(() => {
    getMemos("current").then(setMemos);
  }, []);

  return (
    <section>
      <h1>Memos</h1>
      <p className="muted">One card per company with a decision badge. Placeholder view.</p>
      <div className="grid">
        {memos.map((m) => (
          <article key={m.id} className="card">
            <div className="row">
              <h3>{m.company}</h3>
              <span className={`badge ${m.decision.toLowerCase()}`}>{m.decision}</span>
            </div>
            <p className="muted">{m.founder}</p>
            <p>{m.summary}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
