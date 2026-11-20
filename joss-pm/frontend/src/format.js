export const money = (n) => (n === null || n === undefined || n === "" ? "-" : Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 }));
export const pct = (n) => (n === null || n === undefined ? "-" : `${Number(n).toFixed(1).replace(/\.0$/, "")}%`);
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function date(s) {
  if (!s) return "-";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${Number(m[3])} ${MON[Number(m[2]) - 1]} ${m[1]}` : s;
}
export function dateTime(s) {
  if (!s) return "-";
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
export const human = (k) => String(k).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : "sub-" + Date.now() + "-" + Math.random().toString(16).slice(2));
