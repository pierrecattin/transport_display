import type { Config, Connection, Station } from "../types";

interface Props {
  config: Config;
  onChange: (c: Config) => void;
}

function emptyStation(): Station {
  return { id: "", display_name: "", min_time: 0, connections: [emptyConnection()] };
}
function emptyConnection(): Connection {
  return { number: "", destination: "" };
}

export default function StationsSection({ config, onChange }: Props) {
  const setStations = (stations: Station[]) => onChange({ ...config, stations });

  const patchStation = (i: number, patch: Partial<Station>) =>
    setStations(config.stations.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));

  const move = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= config.stations.length) return;
    const next = config.stations.slice();
    [next[i], next[j]] = [next[j], next[i]];
    setStations(next);
  };

  // The on-screen label for a connection lives in the shared destination_labels
  // map, keyed by the destination string (see src/config.py).
  const labelFor = (dest: string) => config.destination_labels[dest] ?? "";
  const setLabel = (dest: string, label: string) => {
    const labels = { ...config.destination_labels };
    if (label === "") delete labels[dest];
    else labels[dest] = label;
    onChange({ ...config, destination_labels: labels });
  };

  return (
    <section className="card">
      <h2>Stations</h2>
      {config.stations.map((station, i) => (
        <div className="station" key={i}>
          <div className="station-head">
            <div className="grow grid2">
              <label>
                Station ID
                <input
                  value={station.id}
                  onChange={(e) => patchStation(i, { id: e.target.value })}
                  placeholder="8591285"
                />
              </label>
              <label>
                Display name
                <input
                  value={station.display_name}
                  onChange={(e) => patchStation(i, { display_name: e.target.value })}
                  placeholder="Neuaffoltern"
                />
              </label>
              <label>
                Min time (min)
                <input
                  type="number"
                  min={0}
                  value={station.min_time}
                  onChange={(e) =>
                    patchStation(i, { min_time: Math.max(0, Math.floor(Number(e.target.value) || 0)) })
                  }
                />
              </label>
            </div>
            <div className="station-actions">
              <button onClick={() => move(i, -1)} disabled={i === 0} title="Move up">
                ↑
              </button>
              <button
                onClick={() => move(i, 1)}
                disabled={i === config.stations.length - 1}
                title="Move down"
              >
                ↓
              </button>
              <button
                className="danger"
                onClick={() => setStations(config.stations.filter((_, idx) => idx !== i))}
                title="Remove station"
              >
                ✕
              </button>
            </div>
          </div>

          <table className="conns">
            <thead>
              <tr>
                <th>Number</th>
                <th>Destination (API "to")</th>
                <th>Label (on screen)</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {station.connections.map((conn, ci) => {
                const patchConn = (patch: Partial<Connection>) =>
                  patchStation(i, {
                    connections: station.connections.map((c, idx) =>
                      idx === ci ? { ...c, ...patch } : c,
                    ),
                  });
                return (
                  <tr key={ci}>
                    <td>
                      <input
                        className="num"
                        value={conn.number}
                        onChange={(e) => patchConn({ number: e.target.value })}
                        placeholder="32"
                      />
                    </td>
                    <td>
                      <input
                        value={conn.destination}
                        onChange={(e) => patchConn({ destination: e.target.value })}
                        placeholder="Zürich, Strassenverkehrsamt"
                      />
                    </td>
                    <td>
                      <input
                        value={labelFor(conn.destination)}
                        onChange={(e) => setLabel(conn.destination, e.target.value)}
                        placeholder="Strassenverkehrsamt"
                        disabled={!conn.destination}
                      />
                    </td>
                    <td>
                      <button
                        className="danger"
                        onClick={() =>
                          patchStation(i, {
                            connections: station.connections.filter((_, idx) => idx !== ci),
                          })
                        }
                        disabled={station.connections.length === 1}
                        title="Remove connection"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <button
            className="ghost"
            onClick={() =>
              patchStation(i, { connections: [...station.connections, emptyConnection()] })
            }
          >
            + connection
          </button>
        </div>
      ))}
      <button className="ghost" onClick={() => setStations([...config.stations, emptyStation()])}>
        + station
      </button>
    </section>
  );
}
