import type { Config } from "../types";

interface Props {
  config: Config;
  onChange: (c: Config) => void;
}

export default function WeatherSection({ config, onChange }: Props) {
  const setUrl = (url: string) => onChange({ ...config, weather: { url } });

  return (
    <section className="card">
      <h2>Weather</h2>
      <label>
        Gateway live-data URL
        <input
          type="text"
          value={config.weather?.url ?? ""}
          placeholder="http://192.168.1.219/get_livedata_info"
          onChange={(e) => setUrl(e.target.value)}
        />
      </label>
      <p className="muted">
        Ecowitt GW3000 <code>get_livedata_info</code> endpoint; inside/outside
        temperature is shown next to the clock. Leave empty to disable.
      </p>
    </section>
  );
}
