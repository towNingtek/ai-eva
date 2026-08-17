import { useState } from "react";

const SDGS = Array.from({ length: 17 }, (_, i) => [`sdg${i + 1}`, `SDG ${i + 1}`]);
const YEARS = Array.from({ length: 6 }, (_, i) => String(new Date().getFullYear() - i));
const COLORS = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#0891b2"];

export default function ChartAnalysis() {
  const [year, setYear] = useState(props.year || YEARS[0]);
  const [district, setDistrict] = useState(props.district || "");
  const [sdgs, setSdgs] = useState(props.sdgs || ["sdg9", "sdg12"]);
  const toggleSdg = (id) => setSdgs((current) => current.includes(id)
    ? current.filter((value) => value !== id) : [...current, id]);
  const query = () => callAction({ name: "chart_query", payload: { year, district, sdgs } });
  const exportChart = (format) => callAction({ name: "chart_export", payload: { year, district, sdgs, format } });
  const max = Math.max(...(props.items || []).map((item) => item.value || 0), 1);

  return (
    <div className="w-full max-w-3xl rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">年度
          <select className="rounded-md border bg-background p-2" value={year} onChange={(e) => setYear(e.target.value)}>
            {YEARS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-sm">行政區（可留空）
          <input className="rounded-md border bg-background p-2" value={district} onChange={(e) => setDistrict(e.target.value)} placeholder="全區" />
        </label>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {SDGS.map(([id, label]) => <button key={id} className={`rounded-full border px-3 py-1 text-xs ${sdgs.includes(id) ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => toggleSdg(id)}>{label}</button>)}
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <button className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={query} disabled={!sdgs.length || props.loading}>{props.loading ? "查詢中..." : "生成圖表"}</button>
        <button className="rounded-md border px-4 py-2 text-sm" onClick={() => exportChart("pdf")} disabled={!sdgs.length || props.loading}>匯出 PDF</button>
        <button className="rounded-md border px-4 py-2 text-sm" onClick={() => exportChart("png")} disabled={!sdgs.length || props.loading}>匯出 PNG</button>
      </div>
      {props.error && <p className="mb-3 text-sm text-destructive">{props.error}</p>}
      {props.items?.length ? <div className="space-y-3" aria-label="SDG 預算長條圖">
        {props.items.map((item, index) => <div key={item.id} className="grid grid-cols-[4rem_1fr_8rem] items-center gap-2 text-sm"><span>{item.id.toUpperCase()}</span><div className="h-7 rounded bg-muted"><div className="h-7 rounded" style={{ width: `${Math.max(2, (item.value / max) * 100)}%`, backgroundColor: COLORS[index % COLORS.length] }} /></div><span className="text-right">NT$ {(item.value || 0).toLocaleString()}</span></div>)}
        <p className="pt-2 text-sm text-muted-foreground">合計 NT$ {(props.totalBudget || 0).toLocaleString()}，{props.totalProjects || 0} 個專案</p>
      </div> : <p className="text-sm text-muted-foreground">尚未生成圖表。</p>}
    </div>
  );
}
