"""媒合產生內容的四語對照（EPIC #205 / #227；#204 第 4、5 題定案）。

- 規則（標準 YAML、排序設定）只維護**中文一份**；這裡是**顯示用**的對照表，不改 YAML。
  能力類別名稱（B1–B8）、排序規則名稱與原文、狀態與關係名稱、未評估面向……都在這裡。
- 程式組出的句子（建議卡「為何推薦」、欄位「不足」、媒合回覆、流程訊息）用 `msg(key, lang)` 取樣板。
  zh 樣板與修改前的字串一字不差：lang＝zh 時輸出不變。
- 計畫原文引用照「原文＋翻譯」（`app.i18n.quote`）：外文閱讀者看到的引用以原文段標記包起來，
  原文是中文屬正常；有翻譯時附在翻譯段標記內。
- 寫入媒合紀錄與 CMS 的內容不翻（維持中文原文），由呼叫端自己保留中文版。
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.i18n import DEFAULT_LANG, SUPPORTED_LANGS, current_lang, normalize_lang
from app.i18n.quote import _ORIG_CLOSE, _ORIG_OPEN, _TR_CLOSE, _TR_OPEN, TRANSLATION_LABELS


def resolve(lang: Any = None) -> str:
    """lang 省略 → 本連線語言；否則正規化（zh／en／ja／ko）。"""
    return current_lang() if lang is None else normalize_lang(lang)


# ── 能力類別名稱（B1–B8）：中文以標準 YAML capability_registry 為準 ──────────

CAPABILITY_NAMES: dict[str, dict[str, str]] = {
    "B1": {"zh": "空間與場域", "en": "Space & Venues", "ja": "スペースと場づくり", "ko": "공간과 장소"},
    "B2": {"zh": "產品與生產", "en": "Products & Production", "ja": "ものづくりと生産", "ko": "제품과 생산"},
    "B3": {"zh": "服務與體驗", "en": "Services & Experiences", "ja": "サービスと体験", "ko": "서비스와 체험"},
    "B4": {"zh": "內容與品牌", "en": "Content & Branding", "ja": "コンテンツとブランド", "ko": "콘텐츠와 브랜드"},
    "B5": {"zh": "人才與專業", "en": "Talent & Expertise", "ja": "人材とスキル", "ko": "인재와 전문성"},
    "B6": {"zh": "社群與關係", "en": "Community & Relationships", "ja": "コミュニティとつながり",
           "ko": "커뮤니티와 관계"},
    "B7": {"zh": "市場與通路", "en": "Markets & Channels", "ja": "マーケットと販路", "ko": "시장과 유통"},
    "B8": {"zh": "治理與平台", "en": "Governance & Platforms", "ja": "ガバナンスとプラットフォーム",
           "ko": "거버넌스와 플랫폼"},
}


def capability_name(key: str, lang: Any = None, default: str | None = None) -> str:
    """某類能力在 lang 的名稱；表上沒有 → default（或 key）。"""
    entry = CAPABILITY_NAMES.get(key) or {}
    lang = resolve(lang)
    return entry.get(lang) or entry.get(DEFAULT_LANG) or (default if default is not None else key)


def capability_names(lang: Any = None) -> dict[str, str]:
    lang = resolve(lang)
    return {k: capability_name(k, lang) for k in CAPABILITY_NAMES}


# ── 標準／排序設定裡的中文字串（顯示用翻譯；YAML 不改） ────────────────────

TEXT: dict[str, dict[str, str]] = {
    # 排序規則（ranking_profile.yaml）
    "雙向互補優先": {"en": "Two-way complements first", "ja": "おたがいに補いあえるものを優先",
                 "ko": "양방향 보완 우선"},
    "互補候選數多者優先": {"en": "More complement candidates first", "ja": "補完の候補が多いものを優先",
                   "ko": "보완 후보가 많은 쪽 우선"},
    "同分依指定順序": {"en": "Ties follow the order you chose", "ja": "同じ順位なら指定した順番どおり",
                "ko": "동점이면 지정한 순서대로"},
    "A 需要的對方能提供、對方需要的 A 也能提供（雙向互補）排在只有單向互補之前；單向互補排在無互補之前（雙向 2、單向 1、無 0）": {
        "en": "Pairs where the other side can provide what A needs and A can also provide what the other "
              "side needs (two-way complement) rank before one-way complements; one-way complements rank "
              "before no complement (two-way 2, one-way 1, none 0)",
        "ja": "A が必要とするものを相手が提供でき、相手が必要とするものを A も提供できる組み合わせ（おたがいの補いあい）は、"
              "片方だけの補いあいより前に並びます。片方だけの補いあいは、補いあいなしより前に並びます"
              "（おたがい 2、片方だけ 1、なし 0）",
        "ko": "A가 필요로 하는 것을 상대가 제공할 수 있고, 상대가 필요로 하는 것을 A도 제공할 수 있는 경우(양방향 보완)는 "
              "단방향 보완보다 앞에 둡니다. 단방향 보완은 보완 없음보다 앞에 둡니다(양방향 2, 단방향 1, 없음 0)",
    },
    "同一類能力一方 NEED、另一方 OFFER（或 BOTH）算一條互補候選；條數多者在前": {
        "en": "Within the same capability category, one side NEED and the other OFFER (or BOTH) counts as "
              "one complement candidate; more candidates rank first",
        "ja": "おなじ能力のカテゴリで、片方が NEED、もう片方が OFFER（または BOTH）のとき、補いあいの候補を 1 件と数えます。"
              "件数が多いほうが前に並びます",
        "ko": "같은 능력 분류에서 한쪽이 NEED, 다른 쪽이 OFFER(또는 BOTH)이면 보완 후보 1건으로 셉니다. "
              "건수가 많은 쪽이 앞에 옵니다",
    },
    "前面規則都相同時，依使用者指定對象的順序，確保同一 profile 重跑順序相同": {
        "en": "When all earlier rules are equal, follow the order in which the user chose the targets, so "
              "re-running the same profile gives the same order",
        "ja": "それまでのルールがすべて同じときは、ユーザーが指定した相手の順番にしたがいます。"
              "おなじプロファイルで実行しなおしても、おなじ順番になります",
        "ko": "앞의 규칙이 모두 같으면 사용자가 지정한 대상 순서를 따릅니다. 같은 프로필로 다시 실행해도 순서가 같습니다",
    },
    # need_offer 結論（engine）
    "雙向互補": {"en": "two-way complement", "ja": "おたがいに補いあえる", "ko": "양방향 보완"},
    "單向互補": {"en": "one-way complement", "ja": "片方だけ補いあえる", "ko": "단방향 보완"},
    "無互補": {"en": "no complement", "ja": "補いあいなし", "ko": "보완 없음"},
    "成立": {"en": "met", "ja": "あてはまる", "ko": "충족"},
    # 第一期未評估的四維（ranking_profile / out_of_scope）
    "議題與目標對象": {"en": "Topics & target groups", "ja": "テーマと対象となる人たち", "ko": "의제와 대상"},
    "合作可執行性": {"en": "Feasibility of collaboration", "ja": "協力の実現しやすさ", "ko": "협력 실행 가능성"},
    "跨國語境與成本": {"en": "Cross-border context & cost", "ja": "国をこえる文脈とコスト",
                "ko": "국경을 넘는 맥락과 비용"},
    "階段與時程": {"en": "Stage & timeline", "ja": "段階とスケジュール", "ko": "단계와 일정"},
    # 狀態名稱（pair.STATUS_TEXT）
    "先補資料": {"en": "Fill in information first", "ja": "まず情報をおぎなう", "ko": "먼저 정보 보완"},
    "可探索": {"en": "Worth exploring", "ja": "さぐってみる価値あり", "ko": "탐색 가능"},
    "可排序・未建議": {"en": "Rankable, not suggested", "ja": "並べかえ可・おすすめなし",
                "ko": "순위 가능·추천 안 함"},
    "不在範圍": {"en": "Out of scope", "ja": "範囲に入らない", "ko": "범위 밖"},
    # 狀態規則原文（standard status_rules）
    "明確不在目前範圍；保留原因與重新進入條件": {
        "en": "Clearly outside the current scope; the reason and the conditions to re-enter are kept",
        "ja": "いまの範囲にははっきり入りません。理由と、もういちど対象になるための条件をのこします",
        "ko": "현재 범위에서 명확히 벗어납니다. 이유와 다시 포함될 조건을 남겨 둡니다",
    },
    "可能適合但缺關鍵資料；回答補問後重算": {
        "en": "May be a fit but key information is missing; recalculated after the follow-up questions "
              "are answered",
        "ja": "合うかもしれませんが、大事な情報が足りません。追加の質問に答えたあとで計算しなおします",
        "ko": "맞을 수도 있지만 핵심 정보가 부족합니다. 추가 질문에 답하면 다시 계산합니다",
    },
    "具有新穎或部分互補；建議低成本交流": {
        "en": "Novel or partly complementary; a low-cost exchange is suggested",
        "ja": "あたらしさや、部分的な補いあいがあります。まずは手軽な交流をおすすめします",
        "ko": "새롭거나 부분적으로 보완됩니다. 부담 없는 교류를 권합니다",
    },
    "適配與信心達門檻；人類決定是否聯繫": {
        "en": "Fit and confidence reach the threshold; a person decides whether to get in touch",
        "ja": "合いぐあいと確からしさが基準にとどいています。連絡するかどうかは人が決めます",
        "ko": "적합도와 신뢰도가 기준에 이르렀습니다. 연락 여부는 사람이 결정합니다",
    },
    "可進入排序；狀態、權限及最低資料足夠": {
        "en": "Can be ranked; status, permissions and minimum data are sufficient",
        "ja": "並べかえの対象になります。状態・権限・最低限のデータがそろっています",
        "ko": "순위에 들어갈 수 있습니다. 상태, 권한, 최소 데이터가 충분합니다",
    },
    # 關係名稱（pair.REL_*）
    "互補候選": {"en": "Complement candidates", "ja": "補いあいの候補", "ko": "보완 후보"},
    "共同尋找第三方": {"en": "Look for a third party together", "ja": "いっしょに第三者をさがす",
                "ko": "함께 제3자 찾기"},
    "可聯合或交流": {"en": "Joint work or exchange", "ja": "いっしょに動く・交流する", "ko": "공동 추진 또는 교류"},
    # 揭露規則原文（standard bridge_rules）
    "Primary Bridge 成立須有明確 Need、相對應 Offer 及可行合作形式": {
        "en": "A Primary Bridge requires a clear Need, a matching Offer and a workable form of collaboration",
        "ja": "Primary Bridge が成り立つには、はっきりした Need と、それに合う Offer、そして実行できる協力のかたちが必要です",
        "ko": "Primary Bridge가 성립하려면 명확한 Need, 이에 맞는 Offer, 실행 가능한 협력 형태가 있어야 합니다",
    },
    "可推薦共同尋找第三方，但不得標示為互補完成": {
        "en": "May suggest looking for a third party together, but must not be marked as a completed complement",
        "ja": "いっしょに第三者をさがすことはすすめられますが、補いあいが成り立ったとは表示しません",
        "ko": "함께 제3자를 찾도록 권할 수 있지만, 보완이 완료된 것으로 표시해서는 안 됩니다",
    },
    "適合聯合市場、交流或共同擴張，需另行判斷競合": {
        "en": "Suited to joint marketing, exchange or growing together; competition versus cooperation "
              "must be judged separately",
        "ja": "いっしょに売る、交流する、いっしょに広げることに向いています。競合するかどうかは別に判断が必要です",
        "ko": "공동 마케팅, 교류, 함께 확장하기에 적합합니다. 경쟁 여부는 따로 판단해야 합니다",
    },
    # 下一步選項（standard output.next_action_options / cards.NEXT_STEPS）
    "介紹": {"en": "Introduction", "ja": "おたがいの紹介", "ko": "소개"},
    "會議": {"en": "Meeting", "ja": "ミーティング", "ko": "회의"},
    "資料交換": {"en": "Exchange materials", "ja": "資料のやりとり", "ko": "자료 교환"},
    "小型 Pilot": {"en": "Small pilot", "ja": "小さなパイロット", "ko": "소규모 파일럿"},
    "由平台或發起人寄出雙方簡介，先認識彼此": {
        "en": "The platform or the initiator sends both sides' profiles so you can get to know each other first",
        "ja": "プラットフォームか発起人から双方の紹介を送り、まずおたがいを知ります",
        "ko": "플랫폼이나 발의자가 양쪽 소개를 보내 먼저 서로를 알아갑니다",
    },
    "約一次線上或現場會談，確認需求與可提供的內容": {
        "en": "Set up one online or in-person meeting to confirm needs and what can be offered",
        "ja": "オンラインか対面でいちど話しあい、ニーズと提供できることをたしかめます",
        "ko": "온라인이나 현장에서 한 번 만나 필요와 제공 가능한 내용을 확인합니다",
    },
    "交換計畫書、場地或產品資料，評估是否合適": {
        "en": "Exchange project plans, venue or product information to see whether it fits",
        "ja": "計画書や場所、商品の資料をやりとりして、合うかどうかを見ます",
        "ko": "계획서, 장소, 제품 자료를 교환하여 적합한지 살펴봅니다",
    },
    "挑一件小事試做一次，再決定是否擴大合作": {
        "en": "Try one small thing together first, then decide whether to expand the collaboration",
        "ja": "小さなことをひとつためしてから、協力を広げるかどうかを決めます",
        "ko": "작은 일 하나를 먼저 시도해 보고 협력을 넓힐지 결정합니다",
    },
    "以下是可選的下一步，由發起人決定要不要做、先做哪一項": {
        "en": "These are optional next steps; the initiator decides whether to do them and which comes first",
        "ja": "以下はえらべる次のステップです。やるかどうか、どれを先にするかは発起人が決めます",
        "ko": "다음은 선택할 수 있는 다음 단계입니다. 할지, 무엇을 먼저 할지는 발의자가 결정합니다",
    },
    "發起人": {"en": "Initiator", "ja": "発起人", "ko": "발의자"},
    # capability.INFERENCE_LABEL
    "推論（AI，未經 Owner 確認）": {"en": "inference (AI, not confirmed by the Owner)",
                             "ja": "推論（AI によるもので、Owner はまだ確認していません）",
                             "ko": "추론(AI, Owner 미확인)"},
}

_COUNT_RE = re.compile(r"^互補候選 (\d+) 條$")
_COUNT_TEXT = {"en": "{n} complement candidate(s)", "ja": "補いあいの候補 {n} 件", "ko": "보완 후보 {n}건"}


def tr(text: Any, lang: Any = None) -> str:
    """標準／設定裡的中文字串 → lang 的顯示文字。zh 或表上沒有 → 原樣。"""
    s = str(text or "")
    lang = resolve(lang)
    if lang == DEFAULT_LANG or not s:
        return s
    m = _COUNT_RE.match(s)
    if m:
        return _COUNT_TEXT[lang].format(n=m.group(1))
    return (TEXT.get(s) or {}).get(lang) or s


# ── 程式組字樣板（zh 與修改前一字不差） ──────────────────────────────────

MSG: dict[str, dict[str, str]] = {
    # 通用
    "sep": {"zh": "、", "en": ", ", "ja": "、", "ko": ", "},
    "clause_sep": {"zh": "；", "en": "; ", "ja": "。", "ko": "; "},
    "end": {"zh": "。", "en": ".", "ja": "。", "ko": "."},
    "insufficient": {"zh": "不足", "en": "Insufficient", "ja": "根拠が足りません", "ko": "근거 부족"},
    "not_evaluated": {"zh": "未評估", "en": "Not evaluated", "ja": "まだ評価していません", "ko": "평가하지 않음"},
    "capability": {"zh": "能力", "en": "capability", "ja": "能力", "ko": "능력"},
    "all_capabilities": {"zh": "各類能力", "en": "all capability categories", "ja": "それぞれの能力",
                         "ko": "각 능력 분류"},
    "a_default": {"zh": "發起計畫", "en": "the initiating project", "ja": "発起側の計画", "ko": "발의 계획"},
    "t_default": {"zh": "對象計畫", "en": "the target project", "ja": "相手の計画", "ko": "대상 계획"},
    "other_side": {"zh": "對方", "en": "the other side", "ja": "相手", "ko": "상대"},
    # 建議卡欄位標籤（卡片 fields 的鍵維持中文；這是給畫面顯示的標籤）
    "field.為何推薦": {"zh": "為何推薦", "en": "Why recommended", "ja": "おすすめの理由", "ko": "추천 이유"},
    "field.互補性": {"zh": "互補性", "en": "Complementarity", "ja": "補いあえる点", "ko": "상호 보완성"},
    "field.互惠價值": {"zh": "互惠價值", "en": "Mutual benefit", "ja": "おたがいのメリット", "ko": "상호 이익"},
    "field.建議合作": {"zh": "建議合作", "en": "Suggested collaboration", "ja": "おすすめの協力",
                   "ko": "제안 협력"},
    "field.待確認": {"zh": "待確認", "en": "To confirm", "ja": "確認すること", "ko": "확인할 사항"},
    "field.風險": {"zh": "風險", "en": "Risks", "ja": "リスク", "ko": "위험"},
    "field.未評估": {"zh": "未評估", "en": "Not evaluated", "ja": "まだ評価していない観点", "ko": "평가하지 않음"},
    "field.合作起步草案": {"zh": "合作起步草案", "en": "First steps (draft)", "ja": "協力のはじめの一歩（案）",
                     "ko": "협력 시작 초안"},
    # 建議卡：為何推薦
    "why.rule": {"zh": "依規則「{name}」（規則原文：{orig}），本組結果為{res}",
                 "en": "Under the rule \"{name}\" (rule text: {orig}), this pair's result is: {res}",
                 "ja": "ルール「{name}」（ルールの原文：{orig}）により、この組み合わせの結果は「{res}」です",
                 "ko": "규칙 「{name}」(규칙 원문: {orig})에 따라 이 조합의 결과는 「{res}」입니다"},
    "why.evidence": {"zh": "對應原文——", "en": " Matching original text: ", "ja": "対応する原文——",
                     "ko": " 대응 원문: "},
    "why.evidence_line": {"zh": "{cat}：{need}原文{need_q}，{offer}原文{offer_q}",
                          "en": "{cat}: {need} original {need_q}, {offer} original {offer_q}",
                          "ja": "{cat}：{need}の原文{need_q}、{offer}の原文{offer_q}",
                          "ko": "{cat}: {need} 원문 {need_q}, {offer} 원문 {offer_q}"},
    "why.no_evidence": {"zh": "雙方原文依據不足。", "en": " Original-text evidence on both sides is insufficient.",
                        "ja": "双方の原文の根拠が足りません。", "ko": " 양쪽 원문 근거가 부족합니다."},
    "why.ranked": {"zh": "排在第 {rank} 名，依據規則「{name}」。",
                   "en": " Ranked #{rank}, decided by the rule \"{name}\".",
                   "ja": "第 {rank} 位で、ルール「{name}」によって決まりました。",
                   "ko": " 규칙 「{name}」에 따라 {rank}위입니다."},
    # 建議卡：程式組的欄位
    "complement": {"zh": "{a}需要的{caps}，{t}能提供", "en": "{a} needs {caps}, which {t} can provide",
                   "ja": "{a}が必要とする{caps}を、{t}が提供できます",
                   "ko": "{a}에게 필요한 {caps}을(를) {t}이(가) 제공할 수 있습니다"},
    "reciprocity": {"zh": "雙向互惠：{a}得到{x}的支援，{t}得到{y}的支援。",
                    "en": "Mutual benefit: {a} gets support in {x}, and {t} gets support in {y}.",
                    "ja": "おたがいにメリットがあります：{a}は{x}の支援を、{t}は{y}の支援を受けられます。",
                    "ko": "상호 이익: {a}은(는) {x} 지원을, {t}은(는) {y} 지원을 받습니다."},
    "confirm.offer": {"zh": "{name}能否實際提供{cap}（原文未寫明）",
                      "en": "Whether {name} can actually provide {cap} (not stated in the original text)",
                      "ja": "{name}が実際に{cap}を提供できるか（原文にははっきり書かれていません）",
                      "ko": "{name}이(가) 실제로 {cap}을(를) 제공할 수 있는지(원문에 명시되지 않음)"},
    "confirm.third": {"zh": "雙方都需要{caps}，是否要共同找第三方",
                      "en": "Both sides need {caps}; should you look for a third party together",
                      "ja": "双方とも{caps}が必要です。いっしょに第三者をさがすかどうか",
                      "ko": "양쪽 모두 {caps}이(가) 필요합니다. 함께 제3자를 찾을지"},
    # 建議卡：render
    "card.rank": {"zh": "第 {rank} 名：{name}", "en": "#{rank}: {name}", "ja": "第 {rank} 位：{name}",
                  "ko": "{rank}위: {name}"},
    "card.field": {"zh": "【{label}】{value}", "en": "[{label}] {value}", "ja": "【{label}】{value}",
                   "ko": "[{label}] {value}"},
    "card.kv": {"zh": "{k}：{v}", "en": "{k}: {v}", "ja": "{k}：{v}", "ko": "{k}: {v}"},
    "card.draft": {"zh": "{label}：", "en": "{label}: ", "ja": "{label}：", "ko": "{label}: "},
    # 媒合回覆（handler）
    "ma.fact": {"zh": "【事實】", "en": "[Fact] ", "ja": "【事実】", "ko": "[사실] "},
    "ma.infer": {"zh": "【推論】", "en": "[Inference] ", "ja": "【推論】", "ko": "[추론] "},
    "ma.suggest": {"zh": "【建議】", "en": "[Suggestion] ", "ja": "【提案】", "ko": "[제안] "},
    "ma.title": {"zh": "## 媒合分析：{a} × {n} 個指定對象", "en": "## Match analysis: {a} × {n} chosen targets",
                 "ja": "## マッチング分析：{a} × 指定した相手 {n} 件", "ko": "## 매칭 분석: {a} × 지정 대상 {n}개"},
    "ma.status": {"zh": "**狀態：{label}（{status}）**", "en": "**Status: {label} ({status})**",
                  "ja": "**状態：{label}（{status}）**", "ko": "**상태: {label} ({status})**"},
    "ma.status_rule": {"zh": "- {infer}狀態依媒合標準規則、由上述 AI 判斷的方向算出；規則原文：{text}",
                       "en": "- {infer}The status is computed by the matching standard's rules from the "
                             "AI-judged directions above; rule text: {text}",
                       "ja": "- {infer}状態は、上の AI が判断した方向から、マッチング基準のルールで計算しています。"
                             "ルールの原文：{text}",
                       "ko": "- {infer}상태는 위 AI가 판단한 방향으로부터 매칭 기준 규칙에 따라 계산했습니다. "
                             "규칙 원문: {text}"},
    "ma.relation": {"zh": "#### {name}（{n}）", "en": "#### {name} ({n})", "ja": "#### {name}（{n}）",
                    "ko": "#### {name} ({n})"},
    "ma.none": {"zh": "- （無）", "en": "- (none)", "ja": "- （なし）", "ko": "- (없음)"},
    "ma.disclosure": {"zh": "- 揭露規則（媒合標準原文）：{text}",
                      "en": "- Disclosure rule (matching standard text): {text}",
                      "ja": "- 開示ルール（マッチング基準の原文）：{text}",
                      "ko": "- 공개 규칙(매칭 기준 원문): {text}"},
    "ma.complement_item": {"zh": "- {key} {b}：{need} 需要 ← {offer} 可提供",
                           "en": "- {key} {b}: {need} needs ← {offer} can provide",
                           "ja": "- {key} {b}：{need} が必要 ← {offer} が提供できる",
                           "ko": "- {key} {b}: {need} 필요 ← {offer} 제공 가능"},
    "ma.key_item": {"zh": "- {key} {b}", "en": "- {key} {b}", "ja": "- {key} {b}", "ko": "- {key} {b}"},
    "ma.side_fact": {"zh": "    - {fact}{name} 計畫理念原文：{quotes}",
                     "en": "    - {fact}{name} project philosophy, original text: {quotes}",
                     "ja": "    - {fact}{name} の計画理念の原文：{quotes}",
                     "ko": "    - {fact}{name} 계획 이념 원문: {quotes}"},
    "ma.no_quote": {"zh": "（無原文依據）", "en": "(no original-text evidence)", "ja": "（原文の根拠なし）",
                    "ko": "(원문 근거 없음)"},
    "ma.side_infer": {"zh": "    - {infer}{name} 在「{b}」判為 {dir}（{label}）",
                      "en": "    - {infer}{name} is judged {dir} in \"{b}\" ({label})",
                      "ja": "    - {infer}{name} は「{b}」で {dir} と判断（{label}）",
                      "ko": "    - {infer}{name}은(는) 「{b}」에서 {dir}(으)로 판단({label})"},
    "ma.next": {"zh": "#### 下一步", "en": "#### Next step", "ja": "#### 次のステップ", "ko": "#### 다음 단계"},
    "ma.next_clarify": {"zh": "- {s}互補候選還缺需要方「用途」與能提供方「可提供形式」，請先回答下方補問，回答後會依規則重算狀態。",
                        "en": "- {s}The complement candidates still lack the need side's \"purpose\" and the "
                              "offering side's \"form of provision\". Please answer the follow-up question "
                              "below first; the status will then be recalculated by the rules.",
                        "ja": "- {s}補いあいの候補には、必要とする側の「用途」と、提供する側の「提供のかたち」がまだ足りません。"
                              "まず下の追加の質問に答えてください。答えたあと、ルールにしたがって状態を計算しなおします。",
                        "ko": "- {s}보완 후보에는 아직 필요한 쪽의 '용도'와 제공하는 쪽의 '제공 형태'가 빠져 있습니다. "
                              "먼저 아래 추가 질문에 답해 주세요. 답하면 규칙에 따라 상태를 다시 계산합니다."},
    "ma.next_explore": {"zh": "- {s}可考慮低成本交流（{opts}），由 Owner 決定是否採用。",
                        "en": "- {s}Consider a low-cost exchange ({opts}); the Owner decides whether to take it up.",
                        "ja": "- {s}手軽な交流（{opts}）を考えてみてください。とりいれるかどうかは Owner が決めます。",
                        "ko": "- {s}부담 없는 교류({opts})를 고려해 보세요. 채택 여부는 Owner가 결정합니다."},
    "ma.next_none": {"zh": "- {s}目前沒有互補或交流關係；可補充計畫理念後再分析，由 Owner 決定。",
                     "en": "- {s}There is currently no complement or exchange relationship; you can add to the "
                           "project philosophy and analyze again. The Owner decides.",
                     "ja": "- {s}いまは補いあいや交流の関係がありません。計画理念をおぎなってから、もういちど分析できます。"
                           "Owner が決めます。",
                     "ko": "- {s}현재 보완이나 교류 관계가 없습니다. 계획 이념을 보완한 뒤 다시 분석할 수 있습니다. "
                           "Owner가 결정합니다."},
    "ma.disclaimer": {
        "zh": "---\n"
              "**第一期聲明**：本分析只呈現規則與原文，**不推薦**合作對象、**不自動聯絡**任何一方；"
              "AI 不判斷合作意願，是否聯繫由人決定。\n"
              "**未評估的四個維度**：{dims}（未評估不代表不適合）。\n"
              "標示說明：{fact}計畫書原文　{infer}AI 判斷（未經 Owner 確認）　{suggest}下一步選項（由 Owner 決定）",
        "en": "---\n"
              "**Phase 1 notice**: This analysis only shows rules and original text. It does **not recommend** "
              "partners and does **not contact** anyone automatically; AI does not judge willingness to "
              "collaborate, and people decide whether to get in touch.\n"
              "**Four dimensions not evaluated**: {dims} (not evaluated does not mean unsuitable).\n"
              "Legend: {fact}original project text　{infer}AI judgment (not confirmed by the Owner)　"
              "{suggest}next-step options (the Owner decides)",
        "ja": "---\n"
              "**第一期のお知らせ**：この分析はルールと原文をしめすだけで、協力の相手を**おすすめしません**し、"
              "どちらにも**自動で連絡しません**。AI は協力する気持ちを判断しません。連絡するかどうかは人が決めます。\n"
              "**評価していない 4 つの観点**：{dims}（評価していないことは、合わないという意味ではありません）。\n"
              "表示の説明：{fact}計画書の原文　{infer}AI の判断（Owner はまだ確認していません）　"
              "{suggest}次のステップの選択肢（Owner が決めます）",
        "ko": "---\n"
              "**1단계 안내**: 이 분석은 규칙과 원문만 보여 주며, 협력 상대를 **추천하지 않고** 어느 쪽에도 "
              "**자동으로 연락하지 않습니다**. AI는 협력 의사를 판단하지 않으며, 연락 여부는 사람이 결정합니다.\n"
              "**평가하지 않은 네 가지 차원**: {dims} (평가하지 않았다고 해서 적합하지 않다는 뜻은 아닙니다).\n"
              "표시 설명: {fact}계획서 원문　{infer}AI 판단(Owner 미확인)　{suggest}다음 단계 선택지(Owner가 결정)",
    },
    # 媒合分析流程訊息（handler）
    "ma.targets_range": {"zh": "⚠️ 請指定 {lo}–{hi} 個媒合對象（目前 {n} 個）。",
                         "en": "⚠️ Please choose {lo}–{hi} match targets (currently {n}).",
                         "ja": "⚠️ マッチングの相手を {lo}–{hi} 件指定してください（いまは {n} 件）。",
                         "ko": "⚠️ 매칭 대상을 {lo}–{hi}개 지정해 주세요(현재 {n}개)."},
    "ma.run_button": {"zh": "開始媒合分析（{n}）", "en": "Start match analysis ({n})",
                      "ja": "マッチング分析をはじめる（{n}）", "ko": "매칭 분석 시작 ({n})"},
    "ma.pick_targets": {"zh": "A：**{a}**\n請勾選 {lo}–{hi} 個指定對象。已選：{names}",
                        "en": "A: **{a}**\nPlease tick {lo}–{hi} targets. Selected: {names}",
                        "ja": "A：**{a}**\n相手を {lo}–{hi} 件えらんでください。えらんだもの：{names}",
                        "ko": "A: **{a}**\n대상을 {lo}–{hi}개 선택해 주세요. 선택됨: {names}"},
    "ma.none_selected": {"zh": "（尚未勾選）", "en": "(none yet)", "ja": "（まだありません）", "ko": "(아직 없음)"},
    "ma.reenter": {"zh": "⚠️ 請先從 CMS 重新進入 AI-Eva。", "en": "⚠️ Please re-enter AI-Eva from the CMS first.",
                   "ja": "⚠️ まず CMS から AI-Eva に入りなおしてください。",
                   "ko": "⚠️ 먼저 CMS에서 AI-Eva에 다시 들어와 주세요."},
    "ma.list_failed": {"zh": "⚠️ 媒合分析無法讀取專案清單（{exc}）。請確認 CMS 連線與帳號權限後再試。",
                       "en": "⚠️ Match analysis could not read the project list ({exc}). Please check the CMS "
                             "connection and your account permissions, then try again.",
                       "ja": "⚠️ マッチング分析でプロジェクトの一覧を読みこめませんでした（{exc}）。"
                             "CMS への接続とアカウントの権限をたしかめてから、もういちどお試しください。",
                       "ko": "⚠️ 매칭 분석에서 프로젝트 목록을 읽지 못했습니다({exc}). CMS 연결과 계정 권한을 "
                             "확인한 뒤 다시 시도해 주세요."},
    "ma.too_few": {"zh": "⚠️ 媒合分析需要 A 加上至少 {lo} 個對象，目前可用的專案只有 {n} 個。",
                   "en": "⚠️ Match analysis needs A plus at least {lo} targets; only {n} projects are available.",
                   "ja": "⚠️ マッチング分析には A と、すくなくとも {lo} 件の相手が必要です。"
                         "いま使えるプロジェクトは {n} 件だけです。",
                   "ko": "⚠️ 매칭 분석에는 A와 최소 {lo}개의 대상이 필요합니다. 현재 사용할 수 있는 프로젝트는 "
                         "{n}개뿐입니다."},
    "ma.pick_a": {"zh": "🧭 媒合分析：請先選擇你的專案 A。", "en": "🧭 Match analysis: please choose your project A first.",
                  "ja": "🧭 マッチング分析：まず、あなたのプロジェクト A をえらんでください。",
                  "ko": "🧭 매칭 분석: 먼저 내 프로젝트 A를 선택해 주세요."},
    "ma.expired": {"zh": "⚠️ 媒合分析面板已過期，請重新開啟「媒合分析」。",
                   "en": "⚠️ The match analysis panel has expired; please open \"Match analysis\" again.",
                   "ja": "⚠️ マッチング分析のパネルの期限がきれました。「マッチング分析」をもういちど開いてください。",
                   "ko": "⚠️ 매칭 분석 패널이 만료되었습니다. '매칭 분석'을 다시 열어 주세요."},
    "ma.max_targets": {"zh": "⚠️ 最多指定 {hi} 個對象，請先取消其中一個。",
                       "en": "⚠️ You can choose at most {hi} targets; please untick one first.",
                       "ja": "⚠️ 相手は {hi} 件までです。まずどれかひとつをはずしてください。",
                       "ko": "⚠️ 대상은 최대 {hi}개까지입니다. 먼저 하나를 해제해 주세요."},
    # 媒合流程（flow）
    "action.favorite": {"zh": "收藏", "en": "Save", "ja": "お気に入り", "ko": "저장"},
    "action.skip": {"zh": "略過", "en": "Skip", "ja": "スキップ", "ko": "건너뛰기"},
    "action.supplement": {"zh": "補資料", "en": "Add information", "ja": "情報をおぎなう", "ko": "정보 보완"},
    "action.invite": {"zh": "寄站內邀請", "en": "Send an invitation", "ja": "サイト内で招待を送る",
                      "ko": "사이트 내 초대 보내기"},
    # 聊天裡的媒合摘要（task.summary，#229）
    "summary.head": {"zh": "## 🧭 媒合星球：{a} × {n} 個指定對象",
                     "en": "## 🧭 Matching galaxy: {a} × {n} selected project(s)",
                     "ja": "## 🧭 マッチングの星系：{a} × 指定した相手 {n} 件",
                     "ko": "## 🧭 매칭 성계: {a} × 지정한 대상 {n}개"},
    "summary.pair": {"zh": "- **{name}**：{status}（互補候選 {c}・共同尋找第三方 {t}・可聯合或交流 {p}）",
                     "en": "- **{name}**: {status} (complementary candidates {c} · seek a third party together {t}"
                           " · can join forces or exchange {p})",
                     "ja": "- **{name}**：{status}（補いあいの候補 {c}・いっしょに第三者をさがす {t}・連携や交流ができる {p}）",
                     "ko": "- **{name}**: {status} (보완 후보 {c} · 함께 제3자 찾기 {t} · 연대·교류 가능 {p})"},
    "summary.cards": {"zh": "工作區列出 {n} 張媒合建議卡：可收藏、略過、補資料；"
                            "要聯絡對方請按卡片上的「寄站內邀請」並確認，Eva 不會自動寄出。",
                      "en": "The workspace lists {n} match suggestion card(s): you can save, skip or add information. "
                            "To contact the other side, press \"Send an invitation\" on the card and confirm; "
                            "Eva never sends anything automatically.",
                      "ja": "ワークスペースにマッチングの提案カードが {n} 枚あります。お気に入り・スキップ・情報をおぎなうことができます。"
                            "相手に連絡するときは、カードの「サイト内で招待を送る」を押して確認してください。Eva が自動で送ることはありません。",
                      "ko": "작업 공간에 매칭 제안 카드 {n}장이 있습니다. 저장, 건너뛰기, 정보 보완을 할 수 있습니다. "
                            "상대에게 연락하려면 카드의 \"사이트 내 초대 보내기\"를 누르고 확인하세요. "
                            "Eva는 자동으로 보내지 않습니다."},
    "summary.explain": {"zh": "點星球上的衛星或一對，Eva 會用這次的結果說明（不重新判斷）。",
                        "en": "Click a satellite or a pair in the galaxy and Eva will explain it using this result "
                              "(without judging again).",
                        "ja": "星系の衛星やペアを押すと、Eva が今回の結果をもとに説明します（判定のやりなおしはしません）。",
                        "ko": "성계의 위성이나 한 쌍을 누르면 Eva가 이번 결과로 설명합니다(다시 판단하지 않습니다)."},
    "summary.note": {"zh": "第一期不推薦、不自動聯絡；B1–B8 與方向是 AI 推論（未經 Owner 確認）。",
                     "en": "Phase 1 does not recommend or contact anyone automatically; B1–B8 and the directions "
                           "are AI inferences (not confirmed by the Owner).",
                     "ja": "第 1 期は推薦も自動の連絡もしません。B1–B8 と方向は AI の推論です（Owner はまだ確認していません）。",
                     "ko": "1기에는 추천하거나 자동으로 연락하지 않습니다. B1–B8과 방향은 AI 추론입니다(Owner 미확인)."},
    "writeback.ask": {"zh": "要把這段補充寫回計畫書嗎？",
                      "en": "Would you like to add this supplement to your project plan?",
                      "ja": "この補足を計画書に書きもどしますか？",
                      "ko": "이 보충 내용을 계획서에 반영할까요?"},
    # ── #238 媒合準備度（選好 A 時先看資料夠不夠；永不擋開始）──
    "readiness.item.offer": {"zh": "你能提供什麼", "en": "What you can offer",
                             "ja": "提供できること", "ko": "제공할 수 있는 것"},
    "readiness.item.need": {"zh": "你需要什麼", "en": "What you need",
                            "ja": "必要としていること", "ko": "필요한 것"},
    "readiness.item.scale": {"zh": "規模與時間", "en": "Scale and timing",
                             "ja": "規模と時期", "ko": "규모와 시기"},
    "readiness.item.collab": {"zh": "想怎麼合作", "en": "How you want to collaborate",
                              "ja": "どう協力したいか", "ko": "원하는 협력 방식"},
    "readiness.state.ok": {"zh": "足夠", "en": "Enough", "ja": "十分", "ko": "충분"},
    "readiness.state.vague": {"zh": "不夠具體", "en": "Not specific enough",
                              "ja": "具体性が足りない", "ko": "구체적이지 않음"},
    "readiness.state.missing": {"zh": "還沒寫", "en": "Not written yet",
                                "ja": "まだ書かれていない", "ko": "아직 작성되지 않음"},
    "readiness.hint": {"zh": "資料不夠也可以直接媒合；補完推薦會更準",
                       "en": "You can match right away even with missing details; filling them in makes suggestions more accurate",
                       "ja": "情報が足りなくてもそのままマッチングできます。補うと提案がより正確になります",
                       "ko": "정보가 부족해도 바로 매칭할 수 있습니다. 보완하면 추천이 더 정확해집니다"},
    "readiness.complete": {"zh": "資料完整，可以開始", "en": "Details are complete. You can start.",
                           "ja": "情報はそろっています。開始できます", "ko": "정보가 충분합니다. 시작할 수 있습니다"},
    "readiness.ask": {"zh": "回答幾個問題（約 2 分鐘）", "en": "Answer a few questions (about 2 minutes)",
                      "ja": "いくつかの質問に答える（約 2 分）", "ko": "몇 가지 질문에 답하기(약 2분)"},
    "readiness.skip": {"zh": "先直接媒合", "en": "Match right away", "ja": "このままマッチングする",
                       "ko": "바로 매칭하기"},
    "readiness.other": {"zh": "其他（自己寫）", "en": "Other (write your own)", "ja": "その他（自分で書く）",
                        "ko": "기타(직접 작성)"},
    "readiness.stop": {"zh": "先停在這", "en": "Stop here for now", "ja": "ここでやめておく",
                       "ko": "여기서 멈추기"},
    "readiness.consent": {"zh": "要不要補進計畫理念（不會改原本寫的）",
                          "en": "Add this to your project philosophy? (What you already wrote stays unchanged)",
                          "ja": "計画の理念に追記しますか？（元の文章は変えません）",
                          "ko": "계획 이념에 추가할까요?(원래 쓴 내용은 바꾸지 않습니다)"},
    "readiness.q.offer": {"zh": "你的計畫最能拿出來和別人分享的是什麼？",
                          "en": "What can your project most readily share with others?",
                          "ja": "あなたの計画がいちばん人と分かち合えるものは何ですか？",
                          "ko": "당신의 계획이 다른 이와 가장 잘 나눌 수 있는 것은 무엇인가요?"},
    "readiness.q.need": {"zh": "你現在最需要別人幫忙補上的是哪一塊？",
                         "en": "Which part do you most need others to help fill in right now?",
                         "ja": "いま、いちばん誰かに補ってほしい部分はどこですか？",
                         "ko": "지금 다른 이의 도움이 가장 필요한 부분은 무엇인가요?"},
    "readiness.q.scale": {"zh": "這個計畫大概的規模與時間是？",
                          "en": "Roughly what is the scale and timing of this project?",
                          "ja": "この計画のおおよその規模と時期は？",
                          "ko": "이 계획의 대략적인 규모와 시기는 어떻게 되나요?"},
    "readiness.q.collab": {"zh": "你想用什麼方式和夥伴合作？",
                           "en": "How would you like to work with partners?",
                           "ja": "パートナーとどのように協力したいですか？",
                           "ko": "파트너와 어떤 방식으로 협력하고 싶나요?"},
    # 選項以「|」分隔（2–4 個）
    "readiness.opt.offer": {"zh": "場地與空間|專業與人力|產品或在地素材|社群與通路",
                            "en": "Venues and space|Expertise and people|Products or local materials|Community and channels",
                            "ja": "場所とスペース|専門性と人手|製品や地域の素材|コミュニティと販路",
                            "ko": "장소와 공간|전문성과 인력|제품 또는 지역 소재|커뮤니티와 유통"},
    "readiness.opt.need": {"zh": "資金或資源|專業人才|行銷與通路|場地",
                           "en": "Funding or resources|Skilled people|Marketing and channels|Venues",
                           "ja": "資金や資源|専門人材|マーケティングと販路|場所",
                           "ko": "자금 또는 자원|전문 인력|마케팅과 유통|장소"},
    "readiness.opt.scale": {"zh": "小型試辦（3 個月內）|一年期計畫|長期經營（一年以上）",
                            "en": "Small pilot (within 3 months)|One-year project|Long-term (over a year)",
                            "ja": "小規模な試行（3 か月以内）|1 年間の計画|長期運営（1 年以上）",
                            "ko": "소규모 시범(3개월 이내)|1년 계획|장기 운영(1년 이상)"},
    "readiness.opt.collab": {"zh": "共同辦活動|資源互換|長期夥伴關係|一起爭取計畫",
                             "en": "Co-host events|Exchange resources|Long-term partnership|Apply for programs together",
                             "ja": "イベントの共同開催|資源の交換|長期的なパートナー関係|一緒に計画へ応募",
                             "ko": "행사 공동 개최|자원 교환|장기 파트너십|함께 사업 지원"},
}


def msg(key: str, lang: Any = None, /, **kwargs: Any) -> str:
    """取樣板；缺語言退回 zh。"""
    lang = resolve(lang)
    entry = MSG[key]
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**kwargs) if kwargs else text


def field_label(field: str, lang: Any = None) -> str:
    entry = MSG.get(f"field.{field}")
    return (entry.get(resolve(lang)) or entry[DEFAULT_LANG]) if entry else field


def join(items, lang: Any = None) -> str:
    return msg("sep", lang).join(items)


# ── 原文引用（原文＋翻譯） ────────────────────────────────────────────

def quote(text: str, lang: Any = None, translation: str | None = None) -> str:
    """行內引用計畫原文：zh →「原文」（與修改前相同）；外文 → 以原文段標記包起來，有翻譯就附翻譯段。

    標記是 HTML 註解（Markdown 看不到），`app.i18n.quote.extract_original`、
    `app.i18n.llm.strip_zh_gloss` 都認得：原文中文屬正常，不會被當成漏翻。
    """
    lang = resolve(lang)
    body = f"「{text}」"
    if lang == DEFAULT_LANG:
        return body
    out = f"{_ORIG_OPEN}{body}{_ORIG_CLOSE}"
    if translation and translation.strip() and translation.strip() != text:
        out += f"{_TR_OPEN}（{TRANSLATION_LABELS[lang]}：{translation.strip()}）{_TR_CLOSE}"
    return out


_QUOTE_BLOCK = re.compile(
    "(?:" + re.escape(_ORIG_OPEN) + ".*?" + re.escape(_ORIG_CLOSE)
    + "|" + re.escape(_TR_OPEN) + ".*?" + re.escape(_TR_CLOSE) + ")", re.S)


def strip_quotes(text: str) -> str:
    """去掉原文＋翻譯段（檢查「扣掉原文引用後」的文字用）。"""
    return _QUOTE_BLOCK.sub("", text or "")


# ── 寫回詢問的回覆：外文的同意／拒絕 → writeback.parse_consent 認得的中文 ─────────

_NO_REPLY = re.compile(r"いいえ|いや|やめ|結構です|不要|아니|싫|안\s*(?:해|할)|하지\s*마|^\s*no\b|nope|don'?t|not\s+now",
                       re.I)
_YES_REPLY = re.compile(r"^\s*(?:はい|ええ|うん|お願い|おねがい|書きもど|そうして|네|예|응|좋아|그래|반영|부탁)", re.I)


def normalize_consent(reply: Any) -> Any:
    """日韓等外文的「好／不要」換成中文同意詞，其餘原樣（英文 yes/no 本來就認得）。"""
    if not isinstance(reply, str):
        return reply
    if _NO_REPLY.search(reply):
        return "不要"
    if _YES_REPLY.match(reply):
        return "要"
    return reply


__all__ = [
    "CAPABILITY_NAMES",
    "MSG",
    "SUPPORTED_LANGS",
    "TEXT",
    "capability_name",
    "capability_names",
    "field_label",
    "join",
    "msg",
    "normalize_consent",
    "quote",
    "resolve",
    "strip_quotes",
    "tr",
]
