"""Kafka producer para eventos de usuario.

Patrón singleton (mismo que inventory-services). Envelope estándar definido
en notification-services/docs/kafka-topics.md:

    {event_id, event_type, occurred_at, user_id, payload}

Topics que publica este servicio:
  - user-events: user.welcome, user.password_reset, user.email_verification

Si KAFKA_ENABLED=false (local/tests), publish_event() loguea warning y
retorna False. Nunca lanza excepción para no romper el flujo del caller.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

_producer = None


def get_producer():
    """Devuelve la instancia singleton del producer. None si KAFKA_ENABLED=false."""
    global _producer
    if not settings.KAFKA_ENABLED:
        return None
    if _producer is None:
        try:
            from confluent_kafka import Producer

            _producer = Producer(
                {
                    "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                    "client.id": "user-services",
                    "acks": "all",
                    "retries": 3,
                    "linger.ms": 10,
                }
            )
            logger.info("kafka_producer_initialized")
        except Exception as e:
            logger.error("kafka_producer_init_failed: %s", e)
            return None
    return _producer


def _delivery_callback(err, msg):
    if err:
        logger.error("kafka_delivery_failed: %s", err)
    else:
        logger.info(
            "kafka_event_delivered topic=%s partition=%s offset=%s",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )


def publish_user_event(event_type: str, user_id: str, payload: dict) -> bool:
    """Publica un evento de usuario a `user-events` con el envelope estándar.

    Args:
        event_type: e.g. "user.welcome", "user.password_reset"
        user_id: UUID del usuario destinatario (string)
        payload: dict con los campos específicos del event_type
                 (ver notification-services/app/schemas/events.py)

    Returns:
        True si se publicó (o si KAFKA_ENABLED=false — caso local).
        False si Kafka está habilitado pero el producer falló.

    Nunca lanza — el caller no debe fallar si Kafka cae.
    """
    envelope = {
        "event_id": f"{event_type.replace('.', '_')}_{uuid.uuid4()}",
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user_id": str(user_id),
        "payload": payload,
    }
    message = json.dumps(envelope)

    if not settings.KAFKA_ENABLED:
        logger.info("kafka_disabled_event_skipped event_type=%s", event_type)
        return True

    producer = get_producer()
    if producer is None:
        logger.warning("kafka_producer_unavailable event_type=%s", event_type)
        return False

    try:
        producer.produce(
            topic=settings.KAFKA_USER_EVENTS_TOPIC,
            key=str(user_id).encode("utf-8"),
            value=message.encode("utf-8"),
            callback=_delivery_callback,
        )
        producer.poll(0)
        return True
    except Exception as e:
        logger.error("kafka_publish_failed event_type=%s error=%s", event_type, e)
        return False


def close_producer():
    """Flush + cleanup. Llamar en shutdown handler de FastAPI."""
    global _producer
    if _producer:
        _producer.flush(timeout=10)
        _producer = None
