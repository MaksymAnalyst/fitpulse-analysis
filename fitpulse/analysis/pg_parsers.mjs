// Assignment timestamps are UTC stored as PostgreSQL timestamp without time zone.
// Keep SQL text unchanged: JS Date's local-zone parser would shift exported times.
export const utcTextParsers={1082:value=>value,1114:value=>value};
