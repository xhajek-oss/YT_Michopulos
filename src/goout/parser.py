from dataclasses import dataclass
from datetime import datetime


@dataclass
class GoOutEvent:
    schedule_id: int
    event_id: int
    name: str
    description: str | None
    start_at: datetime | None
    end_at: datetime | None
    venue_id: int
    category: str | None
    tags: list[str]
    price: str | None
    currency: str | None
    url: str | None
    image_ids: list[int]
    performer_ids: list[int]
    ticketing_state: str | None
    tickets_url: str | None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(value)


def index_included(data: dict) -> dict:
    included = data.get("included", {})

    return {
        entity_type: {
            entity["id"]: entity
            for entity in entities
        }
        for entity_type, entities in included.items()
    }


def parse_schedule(schedule: dict, included: dict) -> GoOutEvent:
    schedule_attrs = schedule["attributes"]
    relationships = schedule["relationships"]

    event_id = relationships["event"]["id"]
    event = included["events"][event_id]

    event_attrs = event["attributes"]
    event_cs = event.get("locales", {}).get("cs", {})
    event_relationships = event.get("relationships", {})

    venue_id = relationships["venue"]["id"]

    return GoOutEvent(
        schedule_id=schedule["id"],
        event_id=event_id,
        name=event_cs.get("name", ""),
        description=event_cs.get("description"),
        start_at=parse_datetime(schedule_attrs.get("startAt")),
        end_at=parse_datetime(schedule_attrs.get("endAt")),
        venue_id=venue_id,
        category=event_attrs.get("mainCategory"),
        tags=event_attrs.get("tags", []),
        price=schedule_attrs.get("pricing"),
        currency=schedule_attrs.get("currency"),
        url=event_cs.get("siteUrl") or event.get("url"),
        image_ids=[
            image["id"]
            for image in event_relationships.get("images", [])
        ],
        performer_ids=[
            performer["id"]
            for performer in event_relationships.get("performers", [])
        ],
        ticketing_state=schedule_attrs.get("ticketingState"),
        tickets_url=schedule_attrs.get("externalTicketsUrl"),
    )


def parse_events(data: dict) -> list[GoOutEvent]:
    included = index_included(data)

    return [
        parse_schedule(schedule, included)
        for schedule in data.get("schedules", [])
    ]
