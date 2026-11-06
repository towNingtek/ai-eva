import { useEffect, useRef, useState } from "react";

// Wraps the v17 orbit graph (static, /public/tangle/) in an iframe.
// Graph -> backend: postMessage "tangle-relation" -> callAction("tangle_pick").
// Backend -> graph: props.supplements (persisted server-side) -> postMessage "dd-confirmed".
export default function TangleOrbit() {
  const frame = useRef(null);
  const sent = useRef(new Set());
  const [ready, setReady] = useState(false);
  const src = `/public/tangle/tangle-${props.mode}.html?v=${props.v || 1}&p=${encodeURIComponent(props.p || "")}&q=${encodeURIComponent(props.q || "")}`;

  useEffect(() => {
    const onMsg = (e) => {
      if (!frame.current || e.source !== frame.current.contentWindow) return;
      const d = e.data || {};
      if (d.type === "tangle-relation" && d.code) {
        callAction({ name: "tangle_pick", payload: {
          sid: props.sid, mode: props.mode, code: d.code, subject: d.subject, kind: d.kind, tag: d.tag } });
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [props.sid, props.mode]);

  // Replay every server-side supplement into the graph (also after the sidebar is reopened).
  useEffect(() => {
    if (!ready || !frame.current) return;
    for (const s of props.supplements || []) {
      const key = s.subject + ":" + s.code;
      if (sent.current.has(key)) continue;
      frame.current.contentWindow.postMessage({ type: "dd-confirmed", subject: s.subject, code: s.code, text: s.text }, window.location.origin);
      sent.current.add(key);
    }
  }, [ready, props.supplements]);

  return (
    <div className="flex flex-col w-full h-full gap-2">
      <iframe ref={frame} src={src} title="雲林專案星圖" onLoad={() => { sent.current = new Set(); setReady(true); }}
        style={{ width: "100%", height: "calc(100vh - 140px)", minHeight: 420, border: 0, borderRadius: 12, background: "#060a10" }} />
      <p className="text-xs text-muted-foreground">點衛星：在對話中看原文並補充。雲林公開計畫理念固定快照；示範說明非法規條文、不作適用判定。</p>
    </div>
  );
}
