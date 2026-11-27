"""Контракты сообщений Kafka. Названия полей в JSON регистрозависимы."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


class InvalidEvent(ValueError):
    """Сообщение не соответствует контракту или справочнику центра."""


@dataclass(frozen=True)
class CameraEvent:
    event_uuid: UUID
    substation_id: int
    camera_id: int
    occurred_at: datetime


@dataclass(frozen=True)
class CameraStatus(CameraEvent):
    viable: bool


@dataclass(frozen=True)
class CameraDetection(CameraEvent):
    zone_id: int | None
    person_count: int
    confidence: float
    is_alert: bool
    file: str


def positive_int(data: dict, field: str, maximum: int = 2_147_483_647) -> int:
    value = data.get(field)
    if type(value) is not int or not 1 <= value <= maximum:
        raise InvalidEvent(f"{field}: ожидается целое число от 1 до {maximum}")
    return value


def boolean(data: dict, field: str) -> bool:
    value = data.get(field)
    if type(value) is not bool:
        raise InvalidEvent(f"{field}: ожидается true или false")
    return value


def timestamp(data: dict, field: str) -> datetime:
    try:
        instant = datetime.fromisoformat(data.get(field))
        if instant.tzinfo is None:
            raise ValueError
        return instant.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        raise InvalidEvent(f"{field}: ожидается дата ISO 8601 с часовым поясом") from None


def json_object(value: bytes | None) -> dict:
    try:
        data = json.loads((value or b"").decode("utf-8"))
    except (ValueError, RecursionError):
        raise InvalidEvent("Ожидается JSON в UTF-8") from None
    if not isinstance(data, dict):
        raise InvalidEvent("Ожидается JSON-объект")
    return data


def decode_heartbeat(key: bytes | None, value: bytes | None) -> tuple[int, datetime]:
    data = json_object(value)
    node_id = positive_int(data, "node_id")
    if key != str(node_id).encode("ascii"):
        raise InvalidEvent("Ключ Kafka не соответствует node_id")
    return node_id, timestamp(data, "Time")


def decode_event(key: bytes | None, value: bytes | None, *, status: bool) -> CameraStatus | CameraDetection:
    data = json_object(value)
    try:
        if not isinstance(data.get("id"), str):
            raise ValueError
        event_uuid = UUID(data["id"])
    except ValueError:
        raise InvalidEvent("id: ожидается UUID") from None

    station = positive_int(data, "Sender")
    camera = positive_int(data, "Camera_id" if status else "camera_id")
    if key != f"{station}:{camera}".encode("ascii"):
        raise InvalidEvent("Ключ Kafka не соответствует подстанции и камере")
    if status:
        return CameraStatus(event_uuid, station, camera, timestamp(data, "Time"), boolean(data, "Viable"))

    if "zone_id" not in data:
        raise InvalidEvent("Отсутствует zone_id")
    zone = None if data["zone_id"] is None else positive_int(data, "zone_id")
    confidence = data.get("confidence")
    if type(confidence) not in (float, int) or not 0 <= confidence <= 1:
        raise InvalidEvent("confidence: ожидается число от 0 до 1")
    file = data.get("file")
    if not isinstance(file, str) or not file.strip() or "\x00" in file:
        raise InvalidEvent("file: ожидается непустая строка пути")
    try:
        file.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidEvent("file: некорректный Unicode") from None
    return CameraDetection(
        event_uuid, station, camera, timestamp(data, "detected_time"), zone,
        positive_int(data, "person_count", 32767), float(confidence), boolean(data, "is_alert"), file,
    )
