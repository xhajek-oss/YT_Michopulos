from scrapers.idnes import IdnesTVScraper
from storage.sqlite import SQLiteStorage


def main() -> None:
    scraper = IdnesTVScraper()
    storage = SQLiteStorage()
    try:
        programs = scraper.scrape()
        for program in programs:
            storage.upsert_tv_program(program)
            print(
                f"[TV] {program.channel} | {program.start_datetime.isoformat()} | "
                f"{program.title} | id={program.source_id}"
            )
        print(f"[TV] idnes total={len(programs)}")
    finally:
        storage.close()


if __name__ == "__main__":
    main()
