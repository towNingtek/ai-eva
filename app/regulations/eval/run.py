"""對 golden 的 10 案逐一跑正式 judge，結果寫到 <out_dir>/<uuid>.json。

    python -m app.regulations.eval.run <out_dir> [--only uuid,uuid]

計畫書文字取自 plans10.json（雲林正式站快照，清理方式同 regulation_check app）。一輪約 10 分鐘、約 US$20。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

from app.regulations import judge

HERE = Path(__file__).parent


async def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    plans = json.loads((HERE / "plans10.json").read_text(encoding="utf-8"))
    for uuid, p in plans.items():
        if only and uuid not in only:
            continue
        t0 = time.time()
        res = await judge.run_check(p["plan"], "農村再生")
        res["_meta"] = {"uuid": uuid, "name": p["name"], "plan_chars": len(p["plan"]), "seconds": round(time.time() - t0, 1)}
        (out / f"{uuid}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        hit = sum(1 for f in res["findings"] if f["verdict"] == "觸發")
        print(f"{uuid} {p['name'][:14]} {res['_meta']['seconds']}s 觸發 {hit}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
