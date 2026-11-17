import { useState } from "react";

// 專案媒合 1.5（townway#66）：承辦人手動挑選媒合對象。
// options 由後端逐筆推入（一次一批 20 筆）；「載入更多」帶下一批。
export default function MatchPicker() {
  const options = props.options || [];
  const total = props.total || 0;
  const loaded = props.loaded || 0;
  // 後端每次 element.update() 都會重新掛載元件（useState 歸零）。選取狀態
  // 存在 window 上（以 props.pickerId 為 key）跨重掛保留；送 action 時一併帶回後端。
  const store = (window.__matchPicker = window.__matchPicker || {});
  const key = props.pickerId || "default";
  const saved = store[key] || { mine: props.mine || "", partners: props.partners || [], open: !!props.open };
  const [mine, setMineState] = useState(saved.mine);
  const [partners, setPartnersState] = useState(saved.partners);
  const [open, setOpenState] = useState(saved.open);
  const save = (patch) => { store[key] = { mine, partners, open, ...(store[key] || {}), ...patch }; };
  const setMine = (v) => { save({ mine: v }); setMineState(v); };
  const setOpen = (v) => { save({ open: v }); setOpenState(v); };
  const setPartners = (fn) => setPartnersState((cur) => {
    const next = typeof fn === "function" ? fn(cur) : fn;
    save({ partners: next });
    return next;
  });

  const busy = props.loading || props.running;
  const togglePartner = (uuid) => setPartners((cur) => cur.includes(uuid)
    ? cur.filter((u) => u !== uuid) : [...cur, uuid]);
  const chooseMine = (uuid) => {
    setMine(uuid);
    setPartners((cur) => cur.filter((u) => u !== uuid));
  };
  const nameOf = (uuid) => (options.find((o) => o.uuid === uuid) || {}).name || uuid;
  const run = () => callAction({ name: "match_run", payload: { mine, partners } });
  const more = () => callAction({ name: "match_more", payload: { mine, partners, open: true } });
  const candidates = options.filter((o) => o.uuid !== mine);

  return (
    <div className="w-full max-w-3xl rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
      <label className="mb-3 grid gap-1 text-sm">我的專案
        <select className="rounded-md border bg-background p-2" value={mine} onChange={(e) => chooseMine(e.target.value)} disabled={props.running}>
          <option value="">— 請選擇 —</option>
          {options.map((o) => <option key={o.uuid} value={o.uuid}>{o.name}</option>)}
        </select>
      </label>

      <div className="mb-3 text-sm">
        <div className="mb-1">媒合對象（可多選）</div>
        <button type="button" className="w-full rounded-md border bg-background p-2 text-left" onClick={() => setOpen(!open)} disabled={props.running} aria-expanded={open}>
          {partners.length ? `已選 ${partners.length} 個：${partners.map(nameOf).join("、")}` : "— 請勾選 —"}
        </button>
        {open && <div className="mt-1 max-h-72 overflow-y-auto rounded-md border bg-background p-1" role="listbox" aria-multiselectable="true">
          {candidates.map((o) => <label key={o.uuid} className="flex cursor-pointer items-start gap-2 rounded p-2 hover:bg-muted">
            <input type="checkbox" className="mt-1" checked={partners.includes(o.uuid)} onChange={() => togglePartner(o.uuid)} />
            <span>{o.name}{o.period ? <span className="block text-xs text-muted-foreground">{o.period}</span> : null}</span>
          </label>)}
          {props.loading && <div className="p-2 text-xs text-muted-foreground">載入中…（{loaded}/{total}）</div>}
          {!props.loading && loaded < total && <button type="button" className="m-1 rounded-md border px-3 py-1 text-xs" onClick={more}>載入更多（{loaded}/{total}）</button>}
        </div>}
      </div>

      {props.error && <p className="mb-3 text-sm text-destructive">{props.error}</p>}
      <div className="flex items-center gap-3">
        <button className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={run} disabled={!mine || !partners.length || busy}>
          {props.running ? "媒合分析中…" : `開始媒合${partners.length ? `（${partners.length}）` : ""}`}
        </button>
        <span className="text-xs text-muted-foreground">已載入 {loaded}/{total}</span>
      </div>
    </div>
  );
}
