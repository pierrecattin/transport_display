import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  /** Committed to the config while the box is blank; also shown as the placeholder. */
  emptyValue: number;
  onCommit: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  integer?: boolean;
}

// A number input whose text is a local draft, so the user can erase every digit
// without the controlled value snapping back to "0". While blank, `emptyValue`
// is committed and shown greyed-out as the placeholder; blur normalises
// non-blank text to whatever was actually committed (clamped/rounded).
export default function NumberInput({
  value,
  emptyValue,
  onCommit,
  min,
  max,
  step,
  integer = false,
}: Props) {
  const [text, setText] = useState(String(value));
  const committed = useRef(value);

  // Refresh the draft only when the value changed from outside (e.g. config
  // load), never in response to our own commits mid-typing.
  useEffect(() => {
    if (value !== committed.current) {
      committed.current = value;
      setText(String(value));
    }
  }, [value]);

  const commit = (n: number) => {
    committed.current = n;
    onCommit(n);
  };

  const clamp = (n: number) => {
    let v = integer ? Math.round(n) : n;
    if (min !== undefined) v = Math.max(min, v);
    if (max !== undefined) v = Math.min(max, v);
    return v;
  };

  return (
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={text}
      placeholder={String(emptyValue)}
      onChange={(e) => {
        const s = e.target.value;
        setText(s);
        if (s.trim() === "") {
          commit(emptyValue);
        } else {
          const n = Number(s);
          if (!Number.isNaN(n)) commit(clamp(n));
        }
      }}
      onBlur={() => {
        if (text.trim() !== "") setText(String(committed.current));
      }}
    />
  );
}
