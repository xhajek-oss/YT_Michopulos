from src.goout.client import GoOutClient
from src.goout.parser import parse_events


client = GoOutClient()

data = client.get_venue_schedules(65979)

events = parse_events(data)

print(f"Počet akcí: {len(events)}")
print()

for event in events:
    print(f"Název: {event.name}")
    print(f"Datum a čas: {event.start_at}")
    print(f"Cena: {event.price} {event.currency}")
    print(f"Schedule ID: {event.schedule_id}")
    print(f"Event ID: {event.event_id}")
    print(f"URL: {event.url}")
    print("-" * 50)
