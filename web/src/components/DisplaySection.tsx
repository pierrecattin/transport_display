import type { Config, DisplayConfig, Meta } from "../types";

interface Props {
  config: Config;
  meta: Meta;
  onChange: (c: Config) => void;
}

export default function DisplaySection({ config, meta, onChange }: Props) {
  const setField = (key: keyof DisplayConfig, value: number) =>
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
              <input
                type="number"
                min={f.min}
                max={f.max}
                step={f.step}
                value={config.display[f.key]}
                onChange={(e) => {
                  const raw = Number(e.target.value);
                  if (Number.isNaN(raw)) return;
                  setField(f.key, isFloat ? raw : Math.round(raw));
                }}
              />
            </label>
          );
        })}
      </div>
    </section>
  );
}
