import type { ReactNode } from "react";
import type { CitationConfidence, Decision } from "../types";

export function DecisionBadge({ decision }: { decision: Decision }) {
  return <span className={`badge ${decision}`}>{decision.toUpperCase()}</span>;
}

const CONFIDENCE_LABEL: Record<CitationConfidence, string> = {
  verified: "Verified",
  web: "Web",
  inferred: "Inferred",
  unavailable: "Unavailable",
};

export function ConfidenceTag({ level }: { level: CitationConfidence }) {
  return <span className={`ctag ${level}`}>{CONFIDENCE_LABEL[level] ?? level}</span>;
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

/** Renders memo text: **bold**, "- bullet" lines, and plain paragraphs. */
export function RichText({ text }: { text: string }) {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="bullets">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b)}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };

  for (const line of lines) {
    const m = line.match(/^[-•*]\s+(.*)$/);
    if (m) bullets.push(m[1]);
    else {
      flush();
      blocks.push(<p key={`p-${blocks.length}`}>{inline(line)}</p>);
    }
  }
  flush();
  return <div className="rich">{blocks}</div>;
}
