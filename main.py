from scrapers.hcdynamo import HCDynamoScraper
from scrapers.biathlonworld import BiathlonWorldScraper
from scrapers.iihf import IIHFScraper
from scrapers.diamondleague import DiamondLeagueScraper
from scrapers.worldathletics import WorldAthleticsScraper
from storage.sqlite import SQLiteStorage


def main():
    scrapers = [
        HCDynamoScraper(),
        BiathlonWorldScraper(),
        IIHFScraper(),
        DiamondLeagueScraper(),
        WorldAthleticsScraper(),
    ]

    storage = SQLiteStorage()

    try:
        total = 0
        failed = []

        for scraper in scrapers:
            print(f"Scraping {scraper.source}...")

            try:
                events = list(scraper.scrape())
            except Exception as exc:
                failed.append((scraper.source, str(exc)))
                print(f"{scraper.source}: ERROR: {exc}")
                continue

            for event in events:
                storage.upsert(event)

            total += len(events)
            print(f"{scraper.source}: found {len(events)} events")

            for event in events[:5]:
                print(
                    f"  {event.start_datetime.isoformat()} | "
                    f"{event.competition} | {event.name}"
                )

        print(f"Done. Total events processed: {total}")

        if failed:
            print("Sources with errors:")
            for source, error in failed:
                print(f"  {source}: {error}")
    finally:
        storage.close()


if __name__ == "__main__":
    main()
