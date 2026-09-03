from scrapers.hcdynamo import HCDynamoScraper
from scrapers.biathlonworld import BiathlonWorldScraper
from scrapers.iihf import IIHFScraper
from scrapers.diamondleague import DiamondLeagueScraper
from scrapers.worldathletics import WorldAthleticsScraper
from storage.sqlite import SQLiteStorage
from validation.event_validator import EventCountValidator


def main():
    scrapers = [
        HCDynamoScraper(),
        BiathlonWorldScraper(),
        IIHFScraper(),
        DiamondLeagueScraper(),
        WorldAthleticsScraper(),
    ]

    storage = SQLiteStorage()
    validator = EventCountValidator()

    try:
        total = 0
        failed = []
        warning_count = 0

        for scraper in scrapers:
            print(f"Scraping {scraper.source}...")

            try:
                events = list(scraper.scrape())
            except Exception as exc:
                failed.append((scraper.source, str(exc)))
                validator.keep_previous(scraper.source)
                print(f"{scraper.source}: ERROR: {exc}")
                continue

            validation = validator.validate(scraper.source, events)

            if validation.previous_count is None:
                print(
                    f"Validation: {scraper.source} "
                    f"previous=none current={validation.count} BASELINE"
                )
            elif validation.warnings:
                print(
                    f"Validation: {scraper.source} "
                    f"previous={validation.previous_count} "
                    f"current={validation.count} WARNING"
                )
            else:
                print(
                    f"Validation: {scraper.source} "
                    f"previous={validation.previous_count} "
                    f"current={validation.count} OK"
                )

            for warning in validation.warnings:
                warning_count += 1
                print(f"WARNING: {warning}")

            for event in events:
                storage.upsert(event)

            total += len(events)
            print(f"{scraper.source}: found {len(events)} events")

            for event in events[:5]:
                print(
                    f"  {event.start_datetime.isoformat()} | "
                    f"{event.competition} | {event.name}"
                )

        validator.save()

        print(f"Done. Total events processed: {total}")

        if warning_count:
            print(f"Validation warnings: {warning_count}")

        if failed:
            print("Sources with errors:")
            for source, error in failed:
                print(f"  {source}: {error}")
    finally:
        storage.close()


if __name__ == "__main__":
    main()
