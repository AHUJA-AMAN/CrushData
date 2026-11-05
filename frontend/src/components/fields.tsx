import { useId } from "react";
import type { Choice } from "../data/thesisOptions";

export function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="input"
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  choices,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  choices: Choice[];
}) {
  const id = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <select id={id} className="input select" value={value} onChange={(e) => onChange(e.target.value)}>
        {choices.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Multi-select chips: click a chip to toggle it. */
export function ChipGroup({
  label,
  choices,
  value,
  onChange,
}: {
  label: string;
  choices: Choice[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="chip-toggles" role="group" aria-label={label}>
        {choices.map((c) => (
          <button
            key={c.value}
            type="button"
            className={`chip-toggle${value.includes(c.value) ? " on" : ""}`}
            aria-pressed={value.includes(c.value)}
            onClick={() => toggle(c.value)}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Yes / No / Any style toggle (also used for the Solo / Co-founded / Any radio). */
export function Segmented({
  label,
  choices,
  value,
  onChange,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="segmented" role="radiogroup" aria-label={label}>
        {choices.map((c) => (
          <button
            key={c.value}
            type="button"
            role="radio"
            aria-checked={value === c.value}
            className={value === c.value ? "on" : ""}
            onClick={() => onChange(c.value)}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}
