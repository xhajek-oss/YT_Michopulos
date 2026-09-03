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
        for scraper in scrapers:
            print(f"Scraping {scraper.source}...")
            for event in scraper.scrape():
                storage.upsert(event)
    finally:
        storage.close()


if __name__ == "__main__":
    main()
