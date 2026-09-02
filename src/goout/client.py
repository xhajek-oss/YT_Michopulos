import requests


class GoOutClient:
    BASE_URL = "https://goout.net"
    SCHEDULES_URL = f"{BASE_URL}/services/entities/v1/schedules"

    def __init__(self, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        self.timeout = timeout

    def get_venue_schedules(self, venue_id: int, limit: int = 30) -> dict:
        params = [
            ("languages[]", "cs"),
            ("venueIds[]", str(venue_id)),
            ("grouped", "true"),
            ("limit", str(limit)),
            (
                "include",
                "events,images,venues,cities,sales,performers,parents",
            ),
        ]

        response = self.session.get(
            self.SCHEDULES_URL,
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()
