import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { Option } from "../data/thesisOptions";

interface Props {
  label: string;
  placeholder: string;
  options: Option[];
  value: string[];
  onChange: (next: string[]) => void;
  searchable?: boolean;
  emptyText?: string;
  required?: boolean;
  /** Shows a text box inside the menu while the given option is selected (e.g. "Other"). */
  describe?: {
    optionValue: string;
    label: string;
    placeholder: string;
    value: string;
    onChange: (v: string) => void;
  };
}

export default function MultiSelect({
  label,
  placeholder,
  options,
  value,
  onChange,
  searchable = false,
  emptyText = "No options yet.",
  required = false,
  describe,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const describeRef = useRef<HTMLInputElement>(null);
  const menuId = useId();
  const describeId = useId();

  // Close when clicking outside; Escape closes and returns focus to the button.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const selected = useMemo(() => new Set(value), [value]);
  const labelOf = useMemo(() => new Map(options.map((o) => [o.value, o.label])), [options]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) => o.label.toLowerCase().includes(q) || (o.group ?? "").toLowerCase().includes(q),
    );
  }, [options, query]);

  function toggle(v: string) {
    const turningOn = !selected.has(v);
    onChange(turningOn ? [...value, v] : value.filter((x) => x !== v));
    // Move the cursor into the description box as soon as it appears.
    if (turningOn && describe && v === describe.optionValue) {
      window.setTimeout(() => describeRef.current?.focus(), 0);
    }
  }

  const showDescribe = !!describe && selected.has(describe.optionValue);
  const chipLabel = (v: string) => {
    const base = labelOf.get(v) ?? v;
    return describe && v === describe.optionValue && describe.value.trim() ? `${base}: ${describe.value.trim()}` : base;
  };

  // Show chips in the same order as the option list, not click order.
  const orderedValue = useMemo(() => {
    const index = new Map(options.map((o, i) => [o.value, i]));
    return [...value].sort((a, b) => (index.get(a) ?? 0) - (index.get(b) ?? 0));
  }, [options, value]);

  const summary = value.length === 0 ? placeholder : `${value.length} selected`;

  return (
    <div className="field" ref={rootRef}>
      <span className="field-label">
        {label}
        {required && (
          <span className="req" title="Required">
            {" "}
            *
          </span>
        )}
      </span>

      <button
        ref={triggerRef}
        type="button"
        className={`select-trigger${open ? " open" : ""}${value.length ? " has-value" : ""}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{summary}</span>
        <span className="chevron" aria-hidden="true" />
      </button>

      {open && (
        <div className="select-menu" id={menuId} role="group" aria-label={label}>
          {searchable && (
            <input
              className="select-search"
              type="search"
              placeholder={`Search ${label.toLowerCase()}...`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
          )}

          {options.length === 0 ? (
            <p className="select-empty">{emptyText}</p>
          ) : (
            <>
              <div className="select-bar">
                <span className="muted">{value.length} selected</span>
                <button type="button" className="link" onClick={() => onChange([])} disabled={value.length === 0}>
                  Clear
                </button>
              </div>
              <ul className="select-list">
                {visible.map((o) => (
                  <li key={o.value}>
                    <label className={`select-option${o.isGroup ? " group-head" : o.group ? " indent" : ""}`}>
                      <input type="checkbox" checked={selected.has(o.value)} onChange={() => toggle(o.value)} />
                      <span className="box" aria-hidden="true" />
                      <span className="opt-label">{o.label}</span>
                      {o.isGroup && <span className="tag">Continent</span>}
                    </label>
                  </li>
                ))}
                {visible.length === 0 && <li className="select-empty">No matches.</li>}
              </ul>
              {showDescribe && describe && (
                <div className="select-describe">
                  <label className="field-label" htmlFor={describeId}>
                    {describe.label} <span className="req">*</span>
                  </label>
                  <input
                    id={describeId}
                    ref={describeRef}
                    className="input"
                    type="text"
                    value={describe.value}
                    placeholder={describe.placeholder}
                    onChange={(e) => describe.onChange(e.target.value)}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}

      {value.length > 0 && (
        <ul className="chips">
          {orderedValue.map((v) => (
            <li key={v} className="chip">
              <span>{chipLabel(v)}</span>
              <button type="button" aria-label={`Remove ${labelOf.get(v) ?? v}`} onClick={() => toggle(v)}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
