import type { Config } from "../types";

interface Props {
  config: Config;
  fonts: string[];
  onChange: (c: Config) => void;
}

export default function FontsSection({ config, fonts, onChange }: Props) {
  const setFont = (key: "font" | "header_font", value: string) =>
    onChange({ ...config, display: { ...config.display, [key]: value } });

  // Always offer the currently-configured font even if the file list lacks it.
  const options = Array.from(new Set([...fonts, config.display.font, config.display.header_font]));

  return (
    <section className="card">
      <h2>Fonts</h2>
      <div className="grid2">
        <label>
          Body font
          <select value={config.display.font} onChange={(e) => setFont("font", e.target.value)}>
            {options.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label>
          Header font
          <select
            value={config.display.header_font}
            onChange={(e) => setFont("header_font", e.target.value)}
          >
            {options.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}
