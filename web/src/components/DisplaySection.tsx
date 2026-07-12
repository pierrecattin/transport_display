import type { Config, Meta, NumericDisplayKey } from "../types";
import NumberInput from "./NumberInput";

interface Props {
  config: Config;
  meta: Meta;
  onChange: (c: Config) => void;
}

export default function DisplaySection({ config, meta, onChange }: Props) {
  const setField = (key: NumericDisplayKey, value: number) =>
    onChange({ ...config, display: { ...config.display, [key]: value } });

  return (
    <section className="card">
      <h2>Display</h2>
      <div className="grid2">
        {meta.display_fields.map((f) => {
          const isFloat = f.step % 1 !== 0 || f.key === "scroll_px_per_sec";
          return (
            <label key={f.key}>
              {f.label}
              <NumberInput
                min={f.min}
                max={f.max}
                step={f.step}
                integer={!isFloat}
                value={config.display[f.key]}
                emptyValue={meta.display_defaults[f.key]}
                onCommit={(n) => setField(f.key, n)}
              />
            </label>
          );
        })}
      </div>
    </section>
  );
}
