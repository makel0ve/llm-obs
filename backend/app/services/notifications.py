import asyncio
import ipaddress
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urljoin, urlparse

import aiosmtplib
import httpx
import structlog

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.alerts import _validate_https_webhook

log = structlog.get_logger()

MAX_WEBHOOK_REDIRECTS = 3


def alert_cooldown_key(rule_id: object) -> str:
    return f"alert_cooldown:{rule_id}"


def _is_internal_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not ip.is_global


async def _resolve_webhook_host(hostname: str, port: int) -> set[str]:
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            0,
            socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("Webhook host could not be resolved") from exc

    addresses = {str(info[4][0]) for info in infos}
    if not addresses:
        raise ValueError("Webhook host could not be resolved")

    return addresses


async def validate_webhook_delivery_url(url: str) -> str:
    webhook = _validate_https_webhook(url)
    if webhook is None:
        raise ValueError("Webhook URL is required")

    parsed = urlparse(webhook)
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL credentials are not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must include a hostname")

    port = parsed.port or 443
    if port != 443:
        raise ValueError("Webhook URL must use the default HTTPS port")

    try:
        if _is_internal_ip(hostname.strip("[]")):
            raise ValueError("Webhook cannot target private or internal addresses")
    except ValueError as exc:
        if "Webhook cannot target" in str(exc):
            raise

    addresses = await _resolve_webhook_host(hostname, port)
    internal_addresses = [address for address in addresses if _is_internal_ip(address)]
    if internal_addresses:
        raise ValueError("Webhook DNS resolves to private or internal addresses")

    return webhook


class NotificationService:
    async def is_on_cooldown(self, rule_id: object) -> bool:
        redis = await get_redis()
        return bool(await redis.get(alert_cooldown_key(rule_id)))

    async def send_alert(
        self,
        rule: dict[str, Any],
        value: float,
        message: str,
    ) -> bool:
        redis = await get_redis()
        cooldown_key = alert_cooldown_key(rule["id"])

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

    async def _slack(self, rule: dict[str, Any], message: str) -> bool:
        try:
            webhook = await validate_webhook_delivery_url(rule["notify_slack_webhook"])
        except ValueError as e:
            log.warning("slack_webhook_invalid", error=str(e))
            return False

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚨 {rule['name']}"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        ]
        try:
            current_webhook = webhook
            async with httpx.AsyncClient(
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for _ in range(MAX_WEBHOOK_REDIRECTS + 1):
                    current_webhook = await validate_webhook_delivery_url(
                        current_webhook
                    )
                    r = await client.post(current_webhook, json={"blocks": blocks})
                    if not r.is_redirect:
                        break

                    location = r.headers.get("location")
                    if not location:
                        log.warning("slack_redirect_missing_location")
                        return False

                    current_webhook = urljoin(current_webhook, location)
                else:
                    log.warning("slack_redirect_limit_exceeded")
                    return False

                r.raise_for_status()

            return True

        except (ValueError, httpx.HTTPError) as e:
            log.warning("slack_failed", error=str(e))
            return False

    async def _email(
        self,
        rule: dict[str, Any],
        message: str,
        value: float,
    ) -> bool:
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
