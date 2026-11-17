#!/usr/bin/env python3
"""Golden-sample DRAFT for tplanet-multi-tenant#113: which laws each of the 10 plans should trigger.

Independent of the judge: every expected law comes from an explicit, readable rule on the plan text, with the
quoted phrase that triggers it, so the client (甲方／資策會) can confirm or correct each line. The system output is
NOT used to decide the golden (that would score the system against itself); it is only compared afterwards.

Law level (spec: 鄰條／同風險不同條 count as correct). Covered domains only.
Rules (draft, to be confirmed by the client):
  R0 every plan is a 農村再生計畫 → 農村再生條例 (+施行細則); 農村再生計畫審核作業注意事項 (v0.3, yillkid B);
     農村再生計畫審核及執行監督辦法; 農業部補助…審查及管考作業要點;
     農村社區執行農村再生相關計畫經費編列及核銷說明 (funding)
  R1 培根 / 居民座談 / 共識 / 培力 / 課程 → 農村再生培根計畫執行注意事項
  R2 公共設施 / 公共空間 / 活動中心 / 活動空間 → 辦理農村再生相關公共設施作業處理原則
  R3 環境改善 / 綠美化 / 閒置空地整理 / 環境整理 / 髒亂點 → 農村社區自辦整體環境改善作業要點
  R4 個別宅院整建 / 宅院 / 三合院 / 合院 / 古厝立面 → 非都市土地使用管制規則 (建築用地使用)
  R5 公共設施興建或空間改善 (R2 hit) → 非都市土地使用管制規則
  R6 農產加工 / 加工產品 → 農業發展條例 (農業設施／加工)
  R7 農事體驗 / 食農體驗 / 小旅行 / 體驗活動 → 農業發展條例 (休閒農業之母法)
  R8 有機 / 友善農業 / 安全農耕 / 友善土地 → 農業發展條例
  R9 水岸 / 親水 / 步道 / 綠廊 / 自行車道 (linear works along water) → 非都市土地使用管制規則
  R10 山坡地 / 坡地 / 森林 → 水土保持法  (no plan states 山坡地 explicitly; 森林公園 is flagged for review)
  R11 every plan is a community development plan in a non-urban area → 區域計畫法、區域計畫法施行細則、國土計畫法、
     國土計畫法施行細則 (yillkid 2026-11-17: 「算」— a community plan must conform to regional / national land planning)
  Not expected unless the plan states a scale: 環境影響評估法 (no area / household figure in any plan) — the
     judge must answer 需補資訊 there, not 觸發 (spec: 規模門檻 block).
"""
import json
import re
import sys

R11 = ["區域計畫法", "區域計畫法施行細則", "國土計畫法", "國土計畫法施行細則"]
R0 = ["農村再生條例", "農村再生條例施行細則", "農村再生計畫審核作業注意事項", "農村再生計畫審核及執行監督辦法",
      "農業部補助直轄市及縣（市）政府推動社區農村再生計畫審查及管考作業要點",
      "農村社區執行農村再生相關計畫經費編列及核銷說明"]
RULES = [
    ("R1", r"培根|居民座談|共識|培力|課程", ["農村再生培根計畫執行注意事項"]),
    ("R2", r"公共設施|公共空間|活動中心|活動空間", ["辦理農村再生相關公共設施作業處理原則", "非都市土地使用管制規則"]),
    ("R3", r"環境改善|綠美化|閒置空地|環境整理|髒亂點|環境清整", ["農村社區自辦整體環境改善作業要點"]),
    ("R4", r"宅院整建|三合院|合院|古厝", ["非都市土地使用管制規則"]),
    ("R6", r"加工", ["農業發展條例"]),
    ("R7", r"農事體驗|食農體驗|小旅行|體驗活動", ["農業發展條例"]),
    ("R8", r"有機|友善農業|安全農耕|友善土地", ["農業發展條例"]),
    ("R9", r"水岸|親水|步道|綠廊|自行車道", ["非都市土地使用管制規則"]),
    ("R10", r"山坡地|坡地|森林", ["水土保持法"]),
]
REVIEW = {"R10": "計畫只寫「森林公園／森林」，沒寫山坡地；是否屬水土保持範圍請甲方確認"}


def draft(plan):
    expected = {law: ["R0 每案都是農村再生計畫"] for law in R0}
    expected.update({law: ["R11 社區發展計畫應配合區域／國土計畫（yillkid 2026-11-17 確認算觸發）"] for law in R11})
    for rid, pat, laws in RULES:
        m = re.search(pat, plan)
        if m:
            i = m.start()
            quote = plan[max(0, i - 14):i + 18].strip()
            for law in laws:
                expected.setdefault(law, []).append(f"{rid}「…{quote}…」")
    review = [REVIEW[rid] for rid, pat, _ in RULES if rid in REVIEW and re.search(pat, plan)]
    return expected, review


def main():
    plans = json.load(open(sys.argv[1], encoding="utf-8"))  # {uuid: {"name","plan"}}
    out = {"version": "draft-0.3", "unit": "law", "note": "草案，待甲方確認；系統輸出未用於決定 golden",
           "rules": __doc__.split("Rules (draft, to be confirmed by the client):")[1].strip(), "cases": {}}
    for uuid, p in plans.items():
        exp, review = draft(p["plan"])
        out["cases"][uuid] = {"name": p["name"], "expected": sorted(exp), "why": exp, "review": review,
                              "not_expected_note": "環境影響評估法：計畫沒有寫面積／戶數 → 應為需補資訊，不是觸發"}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
