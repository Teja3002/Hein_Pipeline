import logging
import os
from pathlib import Path

from CrossRef.extract import process_folder
from Utilities.app_logging import setup_logging
from Webscraper.databaseScrape import process as process_database_fallback
from Webscraper.recursiveScrape import scrape_from_database_url
from Webscraper.scraper import scrape_from_crossref_result, scrape_without_crossref


def main() -> None:
    log_file = setup_logging()
    project_root = Path(__file__).resolve().parent
    input_dir = project_root / "Input"
    crossref_results_dir = project_root / "CrossRef" / "results"
    webscraper_output_dir = project_root / "Webscraper" / "output"
    webscraper_results_dir = project_root / "Webscraper" / "results"
    process_id = os.getpid()

    logging.info("Application started in main.py with pid=%s", process_id)
    print(f"Logging to {log_file}")

    if not input_dir.exists():
        logging.error("Input folder not found: %s", input_dir)
        print(f"Input folder not found: {input_dir}")
        return

    processed_count = 0

    for folder in sorted(input_dir.iterdir()):
        logging.info("Dispatching folder=%s from main.py", folder.name)
        process_folder(folder.name, str(folder))
        crossref_result_file = crossref_results_dir / f"{folder.name}.json"

        if crossref_result_file.exists():
            logging.info(
                "Starting Webscraper for folder=%s using CrossRef result=%s",
                folder.name,
                crossref_result_file,
            )
            scrape_from_crossref_result(
                folder.name,
                str(crossref_result_file),
                output_dir=str(webscraper_output_dir),
                results_dir=str(webscraper_results_dir),
            )
            processed_count += 1
        else:
            logging.info(
                "No CrossRef result found for folder=%s; starting databaseScrape fallback",
                folder.name,
            )
            fallback_result = process_database_fallback(folder.name)
            logging.info(
                "databaseScrape fallback completed for folder=%s status=%s url=%s",
                folder.name,
                fallback_result.get("status"),
                fallback_result.get("url"),
            )
            if fallback_result.get("status") == "matched":
                logging.info(
                    "Starting recursiveScrape for folder=%s using databaseScrape url=%s",
                    folder.name,
                    fallback_result.get("url"),
                )
                scrape_from_database_url(
                    folder.name,
                    fallback_result["url"],
                    output_dir=str(webscraper_output_dir),
                    results_dir=str(webscraper_results_dir),
                )
                processed_count += 1
            else:
                scrape_without_crossref(folder.name)

    logging.info("Finished processing %s folder(s)", processed_count)
    print(f"Finished processing {processed_count} folder(s)")


if __name__ == "__main__":
    main()
