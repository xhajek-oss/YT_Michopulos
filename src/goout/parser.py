from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata


@dataclass
class GoOutEvent:
    schedule_id: int
    event_id: int
    name: str
    description: str | None
    start_at: datetime | None
    end_at: datetime | None
    venue_id: int
    venue_name: str | None
    address: str | None
    city: str | None
    category: str | None
    tags: list[str]
    price: str | None
    currency: str | None
    url: str | None
    tickets_url: str | None
    image_urls: list[str]
    performer_ids: list[int]
    ticketing_state: str | None


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


def make_goout_url(name: str, event_id: int) -> str:
    """
    Vytvoří standardní českou URL GoOut akce.

    Například:

        Román pro ženy
        3324501

    vytvoří:

        https://goout.net/cs/roman-pro-zeny/events/3324501/
    """

    # Odstranění české diakritiky
    slug = unicodedata.normalize(
        "NFKD",
        name
    ).encode(
        "ascii",
        "ignore"
    ).decode(
        "ascii"
    )

    # Malá písmena
    slug = slug.lower()

    # Všechno kromě písmen a číslic nahradíme pomlčkou
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        slug
    ).strip("-")

    return (
        f"https://goout.net/cs/"
        f"{slug}/events/{event_id}/"
    )


def parse_schedule(schedule: dict, included: dict) -> GoOutEvent:
    schedule_attrs = schedule["attributes"]
    relationships = schedule["relationships"]

    # -------------------------
    # EVENT
    # -------------------------

    event_id = relationships["event"]["id"]
    event = included["events"][event_id]

    event_attrs = event["attributes"]
    event_cs = event.get("locales", {}).get("cs", {})
    event_relationships = event.get("relationships", {})

    # -------------------------
    # VENUE
    # -------------------------

    venue_id = relationships["venue"]["id"]
    venue = included["venues"].get(venue_id, {})

    venue_attrs = venue.get("attributes", {})
    venue_cs = venue.get("locales", {}).get("cs", {})

    # -------------------------
    # PRICE + TICKETS
    # -------------------------

    pricing = schedule_attrs.get("pricing")

    # GoOut někdy vrací do pricing URL
    # externího prodejce místo ceny.
    if pricing and pricing.startswith(
        ("http://", "https://")
    ):
        price = None
    else:
        price = pricing

    tickets_url = schedule_attrs.get(
        "externalTicketsUrl"
    )

    # Pokud není externí prodejce,
    # zkusíme GoOut sale.
    sale_relation = relationships.get("sale")

    if not tickets_url and sale_relation:
        sale_id = sale_relation.get("id")

        sale = included.get(
            "sales",
            {}
        ).get(
            sale_id
        )

        if sale:
            sale_attrs = sale.get(
                "attributes",
                {}
            )

            tickets_url = sale_attrs.get(
                "saleUrl"
            )

    # -------------------------
    # IMAGES
    # -------------------------

    image_urls = []

    for image_relation in event_relationships.get(
        "images",
        []
    ):
        image_id = image_relation["id"]

        image = included.get(
            "images",
            {}
        ).get(
            image_id
        )

        if image:
            image_url = image.get(
                "attributes",
                {}
            ).get(
                "url"
            )

            if image_url:
                image_urls.append(
                    image_url
                )

    # -------------------------
    # EVENT URL
    # -------------------------

    event_name = event_cs.get(
        "name",
        ""
    )

    # Nepoužíváme event.url ani siteUrl,
    # protože GoOut API může vracet zkrácenou
    # URL typu:
    #
    # https://goout.net/event/3324501
    #
    # Místo toho vytvoříme standardní URL.
    event_url = make_goout_url(
        event_name,
        event_id
    )

    # -------------------------
    # RESULT
    # -------------------------

    return GoOutEvent(
        schedule_id=schedule["id"],
        event_id=event_id,

        name=event_name,
        description=event_cs.get(
            "description"
        ),

        start_at=parse_datetime(
            schedule_attrs.get(
                "startAt"
            )
        ),

        end_at=parse_datetime(
            schedule_attrs.get(
                "endAt"
            )
        ),

        venue_id=venue_id,
        venue_name=venue_cs.get(
            "name"
        ),
        address=venue_attrs.get(
            "address"
        ),
        city=venue_attrs.get(
            "city"
        ),

        category=event_attrs.get(
            "mainCategory"
        ),
        tags=event_attrs.get(
            "tags",
            []
        ),

        price=price,
        currency=schedule_attrs.get(
            "currency"
        ),

        url=event_url,

        tickets_url=tickets_url,

        image_urls=image_urls,

        performer_ids=[
            performer["id"]
            for performer in event_relationships.get(
                "performers",
                []
            )
        ],

        ticketing_state=schedule_attrs.get(
            "ticketingState"
        ),
    )


def parse_events(data: dict) -> list[GoOutEvent]:
    included = index_included(data)

    return [
        parse_schedule(
            schedule,
            included
        )
        for schedule in data.get(
            "schedules",
            []
        )
    ]
