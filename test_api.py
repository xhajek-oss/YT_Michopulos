from src.goout.client import GoOutClient


client = GoOutClient()

data = client.get_venue_schedules(65979)

print("Počet schedules:", len(data["schedules"]))
print("Typy included:", list(data["included"].keys()))

for schedule in data["schedules"]:
    print(schedule["id"])
