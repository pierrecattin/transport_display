import type { Config, Meta } from "../types";

interface Props {
  config: Config;
  meta: Meta;
  onChange: (c: Config) => void;
}

export default function ColorsSection({ config, meta, onChange }: Props) {
  const colorFor = (role: string) =>
    config.colors[role] ?? meta.color_defaults[role] ?? "#FFFFFF";

  const setColor = (role: string, value: string) =>
    onChange({ ...config, colors: { ...config.colors, [role]: value.toUpperCase() } });

  return (
    <section className="card">
      <h2>Colors</h2>
      <div className="grid2">
        {meta.color_roles.map((role) => (
          <label key={role.key} className="color-row">
            <span>{role.label}</span>
            <span className="color-input">
              <input
                type="color"
                value={colorFor(role.key)}
                onChange={(e) => setColor(role.key, e.target.value)}
              />
              <code>{colorFor(role.key)}</code>
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}
