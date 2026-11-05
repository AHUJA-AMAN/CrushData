import { useEffect, useState } from "react";
import { getEmails } from "../api";
import type { OutreachEmail } from "../types";

export default function OutreachPanel() {
  const [emails, setEmails] = useState<OutreachEmail[]>([]);

  useEffect(() => {
    getEmails("current").then(setEmails);
  }, []);

  return (
    <section>
      <h1>Outreach</h1>
      <p className="muted">Drafted emails for Meet decisions. Placeholder view.</p>
      <div className="grid">
        {emails.map((e) => (
          <article key={e.memoId} className="card">
            <p className="muted">To: {e.to}</p>
            <h3>{e.subject}</h3>
            <p>{e.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
