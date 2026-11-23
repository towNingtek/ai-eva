"""多輪狀態機的 Chainlit 轉接層（EPIC #174 / #178）。

把 app.loop.core 的 Session 接到對話：

- 一次只送出「下一題」：一則訊息，附「還不知道」「跳過」兩個按鈕。
- 使用者直接打字回答 → 先顯示草稿，附「確認納入」「取消」；按確認才記錄，
  記成「使用者陳述・未查證」；按取消就不記。
- 每次記錄（含還不知道／跳過）後呼叫核心重算；狀態改變時回報「A → B」，沒變也回報「仍是 A」，
  接著問下一題。
- 每一輪的狀態、問題、回答、重算結果都寫進 cl.user_session（JSON 可序列化）。
  Chainlit 會把 user_session 存進 thread metadata、on_chat_resume 時還原，所以重新整理後仍在；
  用 ClarifyLoop.restore() 從 session 重建即可接著問。

Chainlit 物件（Message／Action／user_session）一律從注入的 ``cl`` 取得，
預設才 import chainlit —— 測試可以塞假物件，核心也不因此依賴 UI。
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .core import UNKNOWN, Evaluation, Question, Rules, Session

SESSION_KEY = "clarify_loop"
SOURCE_USER = "使用者陳述・未查證"

LABEL_UNKNOWN = "還不知道"
LABEL_SKIP = "跳過"
LABEL_CONFIRM = "確認納入"
LABEL_CANCEL = "取消"

ACTION_UNKNOWN = "clarify_unknown"
ACTION_SKIP = "clarify_skip"
ACTION_CONFIRM = "clarify_confirm"
ACTION_CANCEL = "clarify_cancel"
ACTIONS = (ACTION_UNKNOWN, ACTION_SKIP, ACTION_CONFIRM, ACTION_CANCEL)

_UNKNOWN_MARK = "__UNKNOWN__"


def _default_cl():
    import chainlit as cl  # 延遲 import：測試用假物件時不需要 chainlit

    return cl


def _enc(value: Any) -> Any:
    return _UNKNOWN_MARK if value is UNKNOWN else value


def _dec(value: Any) -> Any:
    return UNKNOWN if value == _UNKNOWN_MARK else value


def _show(value: Any) -> str:
    return LABEL_UNKNOWN if value is UNKNOWN or value == _UNKNOWN_MARK else str(value)


def transition_text(before: str, after: str) -> str:
    """狀態回報文字：變了 →「A → B」，沒變 →「仍是 A」。"""
    return f"狀態：{before} → {after}" if before != after else f"狀態：仍是 {after}"


class ClarifyLoop:
    """一個對話裡的 clarify loop。狀態全部存在 user_session[key]，物件本身可隨時丟掉重建。"""

    def __init__(self, rules: Rules, cl: Any = None, *, key: str = SESSION_KEY):
        self.rules = rules
        self.cl = cl if cl is not None else _default_cl()
        self.key = key
        data = self._load()
        if data is None:
            data = self._fresh()
        self.data = data
        self.session = Session(
            rules,
            facts={f: _dec(v) for f, v in (data.get("facts") or {}).items()},
            asked=data.get("asked") or [],
        )

    # ── session 存取 ───────────────────────────────────────────────────
    @classmethod
    def restore(cls, rules: Rules, cl: Any = None, *, key: str = SESSION_KEY) -> "ClarifyLoop":
        """從 user_session 重建（on_chat_resume／action callback 用）。"""
        return cls(rules, cl, key=key)

    def _fresh(self) -> dict:
        return {
            "start": self.rules.start,
            "state": None,
            "facts": {},
            "asked": [],
            "records": [],   # 已納入的事實：{field, value, source}
            "pending": None,  # 目前送出、等回答的題目 {field, text}
            "draft": None,    # 打字後、尚未確認的草稿 {field, value}
            "rounds": [],     # 每一輪：{round, question, answer, before, after, changed, next}
            "done": False,
        }

    def _load(self) -> dict | None:
        data = self.cl.user_session.get(self.key)
        return dict(data) if isinstance(data, Mapping) else None

    def _save(self) -> None:
        self.data["facts"] = {f: _enc(v) for f, v in self.session.facts.items()}
        self.data["asked"] = list(self.session.asked)
        self.data["state"] = self.session.state
        self.cl.user_session.set(self.key, self.data)

    # ── 訊息 ──────────────────────────────────────────────────────────
    def _action(self, name: str, label: str, payload: dict) -> Any:
        return self.cl.Action(name=name, label=label, payload=payload)

    async def _send(self, content: str, actions: list | None = None) -> Any:
        if actions:
            msg = self.cl.Message(content=content, actions=actions)
        else:
            msg = self.cl.Message(content=content)
        return await msg.send()

    @staticmethod
    def _qdict(q: Question) -> dict:
        return {"field": q.field, "text": q.text or f"請提供「{q.field}」？"}

    # ── 流程 ──────────────────────────────────────────────────────────
    @property
    def state(self) -> str:
        return self.session.state

    @property
    def pending(self) -> dict | None:
        return self.data.get("pending")

    @property
    def draft(self) -> dict | None:
        return self.data.get("draft")

    @property
    def records(self) -> list[dict]:
        return list(self.data.get("records") or [])

    @property
    def rounds(self) -> list[dict]:
        return list(self.data.get("rounds") or [])

    async def start(self) -> None:
        """開場：回報目前狀態並送出第一題（已有待答題時重送那一題，不重複出新題）。"""
        self._save()
        if self.pending:
            await self._send_question(self.pending)
            return
        await self.ask_next()

    async def ask_next(self) -> dict | None:
        """送出下一題（一次只一題）；沒有題目了就回報結束。"""
        q = self.session.next_question()
        self.data["draft"] = None
        if q is None:
            self.data["pending"] = None
            self.data["done"] = True
            self._save()
            missing = self.session.missing
            tail = f"（仍未補齊：{'、'.join(missing)}）" if missing else ""
            await self._send(f"沒有其他要問的了。目前狀態：{self.state}{tail}")
            return None
        qd = self._qdict(q)
        self.data["pending"] = qd
        self.data["done"] = False
        self._save()
        await self._send_question(qd)
        return qd

    async def _send_question(self, qd: dict) -> None:
        payload = {"field": qd["field"]}
        await self._send(
            qd["text"],
            [
                self._action(ACTION_UNKNOWN, LABEL_UNKNOWN, payload),
                self._action(ACTION_SKIP, LABEL_SKIP, payload),
            ],
        )

    async def on_message(self, text: str) -> bool:
        """使用者直接打字：對目前題目產生草稿，等確認。沒有待答題時回 False（交給別的 handler）。"""
        qd = self.pending
        if not qd:
            return False
        value = (text or "").strip()
        if not value:
            await self._send("沒有收到內容，請再輸入一次，或按「還不知道」「跳過」。")
            return True
        self.data["draft"] = {"field": qd["field"], "value": value}
        self._save()
        payload = {"field": qd["field"]}
        await self._send(
            f"草稿（尚未納入）\n\n**{qd['field']}**：{value}\n\n"
            f"按「{LABEL_CONFIRM}」後才會記錄，標為「{SOURCE_USER}」。",
            [
                self._action(ACTION_CONFIRM, LABEL_CONFIRM, payload),
                self._action(ACTION_CANCEL, LABEL_CANCEL, payload),
            ],
        )
        return True

    async def on_action(self, name: str, payload: Mapping[str, Any] | None = None) -> None:
        payload = dict(payload or {})
        field = payload.get("field")
        qd = self.pending
        # 舊訊息上的按鈕（題目已換）一律忽略，避免重複記錄
        if not qd or (field is not None and field != qd["field"]):
            await self._send("這個按鈕已過期，請回答目前的問題。")
            return
        if name == ACTION_CONFIRM:
            draft = self.draft
            if not draft or draft["field"] != qd["field"]:
                await self._send("沒有待確認的草稿。")
                return
            await self._record(qd, "answer", draft["value"])
        elif name == ACTION_CANCEL:
            self.data["draft"] = None
            self._save()
            await self._send(f"已取消，沒有記錄。請重新回答：{qd['text']}")
        elif name == ACTION_UNKNOWN:
            await self._record(qd, "unknown", UNKNOWN)
        elif name == ACTION_SKIP:
            await self._record(qd, "skip", None)
        else:
            raise ValueError(f"unknown clarify action: {name}")

    async def _record(self, qd: dict, kind: str, value: Any) -> Evaluation:
        before = self.session.state
        f = qd["field"]
        if kind == "answer":
            ev = self.session.answer(f, value)
        elif kind == "unknown":
            ev = self.session.unknown(f)
        else:
            ev = self.session.skip(f)
        answer: dict = {"kind": kind, "value": None if kind == "skip" else _enc(self.session.facts.get(f))}
        if kind != "skip":
            answer["source"] = SOURCE_USER
            self.data["records"] = [r for r in self.records if r["field"] != f] + [
                {"field": f, "value": answer["value"], "source": SOURCE_USER}
            ]
        after = ev.state
        self.data["rounds"] = self.rounds + [{
            "round": len(self.rounds) + 1,
            "question": dict(qd),
            "answer": answer,
            "before": before,
            "after": after,
            "changed": before != after,
            "missing": list(ev.missing),
            "missing_minimum": list(ev.missing_minimum),
        }]
        self.data["draft"] = None
        self.data["pending"] = None
        self._save()

        if kind == "skip":
            head = f"已跳過「{f}」。"
        else:
            head = f"已記錄「{f}」：{_show(answer['value'])}（{SOURCE_USER}）。"
        await self._send(f"{head}\n\n{transition_text(before, after)}")
        await self.ask_next()
        return ev


def register_action_callbacks(rules_for_session: Callable[[], Rules], cl: Any = None,
                              *, key: str = SESSION_KEY) -> None:
    """把四個按鈕註冊成 Chainlit action callback。

    rules_for_session：回傳本對話用的 Rules（例如依 app 讀對應 YAML）。
    """
    cl = cl if cl is not None else _default_cl()

    def make(name: str):
        async def _cb(action):
            loop = ClarifyLoop.restore(rules_for_session(), cl, key=key)
            await loop.on_action(name, getattr(action, "payload", None) or {})

        _cb.__name__ = f"_on_{name}"
        return _cb

    for name in ACTIONS:
        cl.action_callback(name)(make(name))


__all__ = [
    "ACTIONS", "ACTION_CANCEL", "ACTION_CONFIRM", "ACTION_SKIP", "ACTION_UNKNOWN",
    "ClarifyLoop", "LABEL_CANCEL", "LABEL_CONFIRM", "LABEL_SKIP", "LABEL_UNKNOWN",
    "SESSION_KEY", "SOURCE_USER", "register_action_callbacks", "transition_text",
]
