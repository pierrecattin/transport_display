import { useEffect, useState } from "react";
import { getConfig, getFonts, getMeta, putConfig } from "./api";
import type { Config, Meta } from "./types";
import StationsSection from "./components/StationsSection";
import DisplaySection from "./components/DisplaySection";
import FontsSection from "./components/FontsSection";
import ColorsSection from "./components/ColorsSection";
import Preview from "./components/Preview";

type Banner = { kind: "ok" | "error" | "info"; text: string };

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [fonts, setFonts] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);

  useEffect(() => {
    Promise.all([getConfig(), getMeta(), getFonts()])
      .then(([c, m, f]) => {
        setConfig(c);
        setMeta(m);
        setFonts(f);
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setBanner({ kind: "info", text: "Saving and restarting the display…" });
    try {
      const res = await putConfig(config);
      setBanner({
        kind: "ok",
        text: res.restart.ok
          ? "Saved. Display restarting."
          : `Saved. Restart skipped: ${res.restart.detail}`,
      });
    } catch (e: unknown) {
      setBanner({ kind: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  if (loadError) return <div className="page error">Failed to load: {loadError}</div>;
  if (!config || !meta) return <div className="page muted">Loading…</div>;

  return (
    <div className="page">
      <header className="topbar">
        <h1>LED display config</h1>
        <button className="primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save & Apply"}
        </button>
      </header>
      {banner && <div className={`banner ${banner.kind}`}>{banner.text}</div>}

      <div className="layout">
        <main className="form">
          <StationsSection config={config} onChange={setConfig} />
          <DisplaySection config={config} meta={meta} onChange={setConfig} />
          <FontsSection config={config} fonts={fonts} onChange={setConfig} />
          <ColorsSection config={config} meta={meta} onChange={setConfig} />
        </main>
        <aside className="side">
          <Preview config={config} />
        </aside>
      </div>
    </div>
  );
}
