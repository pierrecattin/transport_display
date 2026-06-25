import { useEffect, useState } from "react";
import { fetchPreview } from "../api";
import type { Config } from "../types";

interface Props {
  config: Config;
}

// Debounced live render of the (unsaved) config, so colour/font/label edits are
// visible before applying. The backend renders with the pure-PIL layout, so this
// never touches the panel.
export default function Preview({ config }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    const timer = setTimeout(() => {
      fetchPreview(config, 4)
        .then((u) => {
          if (cancelled) {
            URL.revokeObjectURL(u);
            return;
          }
          objectUrl = u;
          setError(null);
          setUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return u;
          });
        })
        .catch((e: unknown) => {
          if (!cancelled) setError(e instanceof Error ? e.message : String(e));
        });
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [config]);

  return (
    <div className="preview">
      <h2>Live preview</h2>
      <div className="preview-frame">
        {url ? <img src={url} alt="panel preview" /> : <span className="muted">rendering…</span>}
      </div>
      {error && <p className="error">Preview error: {error}</p>}
      <p className="muted small">128×64 panel, sample departures. Not the live panel.</p>
    </div>
  );
}
