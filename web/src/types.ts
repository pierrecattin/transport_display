// Mirrors the shape of config.json (see src/config.py).

export interface Connection {
  number: string;
  destination: string;
}

export interface Station {
  id: string;
  display_name: string;
  min_time: number;
  connections: Connection[];
}

export interface DisplayConfig {
  brightness: number;
  poll_interval_sec: number;
  api_limit: number;
  scroll_px_per_sec: number;
  font: string;
  header_font: string;
  gpio_slowdown: number;
  pwm_bits: number;
  pwm_lsb_nanoseconds: number;
}

export interface WeatherConfig {
  url: string; // GW3000 get_livedata_info endpoint; empty disables the feature
}

export interface Config {
  stations: Station[];
  destination_labels: Record<string, string>;
  display: DisplayConfig;
  colors: Record<string, string>; // role -> "#RRGGBB"
  weather?: WeatherConfig; // optional: older configs predate it
}

// The display keys with numeric values (the fonts are edited elsewhere).
export type NumericDisplayKey = {
  [K in keyof DisplayConfig]: DisplayConfig[K] extends number ? K : never;
}[keyof DisplayConfig];

export interface DisplayField {
  key: NumericDisplayKey;
  label: string;
  min: number;
  max: number;
  step: number;
}

export interface ColorRole {
  key: string;
  label: string;
}

export interface Meta {
  display_defaults: DisplayConfig;
  display_fields: DisplayField[];
  color_defaults: Record<string, string>;
  color_roles: ColorRole[];
}
