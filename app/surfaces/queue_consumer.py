"""RabbitMQ consumer — 訂閱 line-push queue → push 給 LINE user。

訊息格式（producer 必須遵守）：
    {
        "user_id": "U...",
        "text": "要推播的內容",
        "source": "pi5-eva-daily"     # 可選，給 log 用
    }

啟動方式：Chainlit 啟動時 fire-and-forget asyncio task（main.py 內 import 即註冊）。
"""
import asyncio
import json
import logging
import os

import aio_pika

from app.surfaces.line import push_to_user

logger = logging.getLogger(__name__)

_RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
_QUEUE = os.getenv("RABBITMQ_QUEUE", "line-push")


async def _process_message(msg: aio_pika.IncomingMessage) -> None:
    async with msg.process():   # auto-ack on success, requeue on exception
        try:
            payload = json.loads(msg.body)
        except json.JSONDecodeError:
            logger.error("queue payload not JSON: %r", msg.body[:200])
            return

        user_id = payload.get("user_id")
        text = payload.get("text")
        source = payload.get("source", "unknown")
        if not user_id or not text:
            logger.error("queue payload missing user_id/text: %s", payload)
            return

        logger.info("push (src=%s) to %s: %r", source, user_id, text[:80])
        ok = await push_to_user(user_id, text)
        if not ok:
            logger.warning("push_to_user returned False (user_id=%s)", user_id)


async def _consume_loop() -> None:
    if not _RABBITMQ_URL:
        logger.warning("RABBITMQ_URL not set; queue consumer disabled")
        return

    while True:
        try:
            logger.info("connecting RabbitMQ at %s", _RABBITMQ_URL.split("@")[-1])
            conn = await aio_pika.connect_robust(_RABBITMQ_URL)
            async with conn:
                channel = await conn.channel()
                await channel.set_qos(prefetch_count=10)
                queue = await channel.declare_queue(_QUEUE, durable=True)
                logger.info("listening on queue=%s", _QUEUE)
                await queue.consume(_process_message)
                # idle forever — connect_robust 會自己處理斷線重連
                await asyncio.Future()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("queue consumer crashed; retry in 10s: %s", e)
            await asyncio.sleep(10)


def start_in_background() -> asyncio.Task | None:
    """Chainlit 沒有 on_app_startup decorator，main.py 直接 import + 呼叫這個。"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return None
    return loop.create_task(_consume_loop(), name="rabbitmq-consumer")
