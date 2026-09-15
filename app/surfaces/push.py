"""RabbitMQ publisher —— ai-eva 主動把訊息丟進推播佇列。

queue_consumer.py 是**收**的那一半（訂 `line-push` → 轉發 LINE），一直以來
producer 都在 ai-eva 外面（pi5 cron）。法規檢核要走 PUSH（提交 → 稍後回報告），
ai-eva 得學會發訊息，所以補上這一半。

刻意沿用同一條 `line-push` queue 與同一個 payload 格式：
    {"user_id": "U...", "text": "...", "source": "regulation-check"}
consumer 一行都不用改 —— 少動 core 一次。

沒設 RABBITMQ_URL 就 no-op 回 False（本機開發、CI 不會因此炸掉）。
"""
from __future__ import annotations

import json
import logging
import os

import aio_pika

logger = logging.getLogger(__name__)

_RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
_QUEUE = os.getenv("RABBITMQ_QUEUE", "line-push")


async def push_line(user_id: str, text: str, *, source: str = "ai-eva") -> bool:
    """丟一則 LINE 推播進佇列。回傳有沒有成功入列（不代表已送達）。"""
    if not _RABBITMQ_URL:
        logger.info("RABBITMQ_URL 未設定，略過推播（source=%s）", source)
        return False
    if not user_id or not text:
        return False
    try:
        conn = await aio_pika.connect_robust(_RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            await channel.declare_queue(_QUEUE, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps({"user_id": user_id, "text": text, "source": source},
                                    ensure_ascii=False).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=_QUEUE,
            )
        logger.info("已入列推播 source=%s user=%s len=%d", source, user_id[:8], len(text))
        return True
    except Exception as e:  # noqa: BLE001
        logger.exception("推播入列失敗（source=%s）：%s", source, e)
        return False
