import logging
import os
import subprocess
import sys
from pathlib import Path

from Combinator.combine_results import combine_folder as combine_folder_results
from CrossRef.extract import process_folder
from Utilities.app_logging import setup_logging
from Webscraper.databaseScrape import process as process_database_fallback
from Webscraper.recursiveScrape import scrape_from_database_url
from Webscraper.scraper import scrape_from_crossref_result, scrape_without_crossref


def start_ocr_pipeline(folder_name, folder_path, llm_dir):
    ocr_script = llm_dir / "ocr_pipeline.py"
    command = [sys.executable, str(ocr_script), str(folder_path)]
    process = subprocess.Popen(
        command,
        cwd=str(llm_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    logging.info(
        "Started OCR pipeline asynchronously for folder=%s pid=%s command=%s cwd=%s",
        folder_name,
        process.pid,
        command,
        llm_dir,
    )
    return process


def wait_for_ocr_pipeline(folder_name, ocr_process):
    logging.info(
        "Waiting for OCR pipeline process to finish for folder=%s child_pid=%s",
        folder_name,
        ocr_process.pid,
    )
    stdout, stderr = ocr_process.communicate()

    if ocr_process.returncode == 0:
        logging.info(
            "OCR pipeline completed for folder=%s pid=%s",
            folder_name,
            ocr_process.pid,
        )
    else:
        logging.error(
            "OCR pipeline failed for folder=%s pid=%s returncode=%s stderr=%s",
            folder_name,
            ocr_process.pid,
            ocr_process.returncode,
            stderr.strip(),
        )

    if stdout.strip():
        logging.info("OCR pipeline stdout for folder=%s:\n%s", folder_name, stdout.strip())
    if stderr.strip() and ocr_process.returncode == 0:
        logging.warning("OCR pipeline stderr for folder=%s:\n%s", folder_name, stderr.strip())


def main() -> None:
    log_file = setup_logging()
    project_root = Path(__file__).resolve().parent
    input_dir = project_root / "Input"
    crossref_results_dir = project_root / "CrossRef" / "results"
    webscraper_output_dir = project_root / "Webscraper" / "output"
    webscraper_results_dir = project_root / "Webscraper" / "results"
    llm_dir = project_root / "LLM"
    process_id = os.getpid()

    logging.info("Application started in main.py with pid=%s", process_id)
    print(f"Logging to {log_file}")

    if not input_dir.exists():
        logging.error("Input folder not found: %s", input_dir)
        print(f"Input folder not found: {input_dir}")
        return

    processed_count = 0


    print(f"Found {len(list(input_dir.iterdir()))} folder(s) in Input directory '{input_dir}':") 

    for folder in sorted(input_dir.iterdir()):
        print(f"Dispatching folder '{folder.name}' for processing...") 

        break

    for folder in sorted(input_dir.iterdir()):
        logging.info(
            "Dispatching folder=%s from main.py main_pid=%s",
            folder.name,
            process_id,
        )
        ocr_process = start_ocr_pipeline(folder.name, folder, llm_dir)
        logging.info(
            "Current process state for folder=%s main_pid=%s ocr_pid=%s ocr_input_path=%s",
            folder.name,
            process_id,
            ocr_process.pid,
            folder,
        )
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

        wait_for_ocr_pipeline(folder.name, ocr_process)
        logging.info("Starting combinator for folder=%s after OCR wait", folder.name)
        combine_folder_results(folder.name)
        logging.info("Finished combinator for folder=%s", folder.name)

    logging.info("Finished processing %s folder(s)", processed_count)
    print(f"Finished processing {processed_count} folder(s)")


if __name__ == "__main__":
    main()
