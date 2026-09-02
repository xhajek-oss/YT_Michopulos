import json
from pathlib import Path

from src.goout.client import GoOutClient
from src.goout.parser import parse_events


client = GoOutClient()

# Načtení dat z GoOut API
data = client.get_venue_schedules(65979)

# Uložení skutečné API odpovědi jako testovací fixture
fixture_path = Path("tests/fixtures/goout_hronovicka.json")

fixture_path.parent.mkdir(parents=True, exist_ok=True)

with fixture_path.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"API odpověď uložena do: {fixture_path}")
print()

# Zpracování API dat pomocí parseru
events = parse_events(data)

print(f"Počet akcí: {len(events)}")
print()

for event in events:
    print(f"Název: {event.name}")
    print(f"Datum a čas: {event.start_at}")
    print(f"Místo: {event.venue_name}")
    print(f"Adresa: {event.address}")
    print(f"Město: {event.city}")
    print(f"Kategorie: {event.category}")
    print(f"Cena: {event.price} {event.currency}")
    print(f"Vstupenky: {event.tickets_url}")
    print(f"Obrázků: {len(event.image_urls)}")
    print(
        f"První obrázek: "
        f"{event.image_urls[0] if event.image_urls else None}"
    )
    print(f"Schedule ID: {event.schedule_id}")
    print(f"Event ID: {event.event_id}")
    print(f"Ticketing state: {event.ticketing_state}")
    print("-" * 50)
