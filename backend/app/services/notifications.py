from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx
import structlog

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.alerts import _validate_https_webhook

log = structlog.get_logger()


class NotificationService:
    async def send_alert(self, rule: dict, value: float, message: str) -> bool:
        redis = await get_redis()
        cooldown_key = f"alert_cooldown:{rule['id']}"

        if await redis.get(cooldown_key):
            log.debug("alert_suppressed_cooldown", rule_id=str(rule["id"]))
            return False

        sent = False
        if rule["notify_slack_webhook"]:
            sent |= await self._slack(rule, message)

        if rule["notify_email"]:
            sent |= await self._email(rule, message, value)

        if sent:
            await redis.set(cooldown_key, "1", ex=rule["cooldown_minutes"] * 60)

        return sent

    async def _slack(self, rule: dict, message: str) -> bool:
        try:
            webhook = _validate_https_webhook(rule["notify_slack_webhook"])
        except ValueError as e:
            log.warning("slack_webhook_invalid", error=str(e))
            return False

        if webhook is None:
            return False

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚨 {rule['name']}"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        ]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(webhook, json={"blocks": blocks})
                r.raise_for_status()

            return True

        except Exception as e:
            log.warning("slack_failed", error=str(e))
            return False

    async def _email(self, rule: dict, message: str, value: float) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🚨 Alert: {rule['name']}"
            msg["From"] = settings.smtp_from
            msg["To"] = rule["notify_email"]

            body = f"""
                Alert: {rule["name"]}
                Value: {value}

                {message}
            """.strip()

            msg.attach(MIMEText(body, "plain"))

            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_password.get_secret_value() or None,
                start_tls=settings.smtp_port == 587,
            )

            log.info("email_sent", email=rule["notify_email"], rule=rule["name"])
            return True

        except Exception as e:
            log.warning("email_failed", email=rule["notify_email"], error=str(e))
            return False
