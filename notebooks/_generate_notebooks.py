"""
One-off helper to emit .ipynb JSON. Not required at runtime.
"""
import json
from pathlib import Path

NB_VERSION = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11.0"}}}


def cells_to_nb(cells):
    return {**NB_VERSION, "cells": cells}


def md(lines):
    return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in lines]}


def code(lines):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [l + "\n" for l in lines]}


ROOT_RESOLVE = """from pathlib import Path
import os
import sys

def resolve_project_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "Input").is_dir():
        return cwd
    if (cwd.parent / "Input").is_dir():
        return cwd.parent
    return cwd

PROJECT_ROOT = resolve_project_root()
repo_root_str = str(PROJECT_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)
os.chdir(PROJECT_ROOT)"""


def write(name, cells):
    path = Path(__file__).parent / name
    path.write_text(json.dumps(cells_to_nb(cells), indent=2), encoding="utf-8")
    print("wrote", path)


def main():
    write(
        "00_environment.ipynb",
        [
            md(
                [
                    "# Environment",
                    "",
                    "Run this notebook first (optional). It sets **project root**, `sys.path`, and working directory so imports match `python main.py` from the repo root.",
                    "",
                    "Works whether Jupyter’s current directory is the repository root or `notebooks/`.",
                    "",
                    "**Notebook index** (same folder):",
                    "- `01_full_pipeline` — end-to-end pipeline (`main.py`)",
                    "- `02_evaluation` — `evaluation.py`",
                    "- `03_evaluation_compare` — `evaluation_compare.py`",
                    "- `04_stage_crossref` — CrossRef only",
                    "- `05_stage_llm_ocr` — LLM OCR pipeline",
                    "- `06_stage_combinator` — combiner v2",
                    "- `07_stage_converter_dispatch` — converter manager",
                    "- `08_validator_yml_compare` — YML validation",
                    "- `09_utilities_archive_outputs` — archive outputs",
                    "- `10_llm_extract_doi` — DOI extraction (run from `LLM/`)",
                    "- `11_webscraper_database_scrape` — database URL lookup",
                    "- `12_webscraper_full_crawl_demo` — crawl demo (network-heavy)",
                    "- `13_combinator_v1_batch` — legacy combiner batch",
                    "- `14_evaluation_subscores` — EvaluationScript-only scores",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "assert (PROJECT_ROOT / 'main.py').exists(), f'Expected repo root with main.py: {PROJECT_ROOT}'",
                    "print('PROJECT_ROOT =', PROJECT_ROOT)",
                    "for name in ('Input', 'CrossRef', 'LLM', 'Webscraper', 'Combinator', 'Converter'):",
                    "    p = PROJECT_ROOT / name",
                    "    print(f'  [{('OK' if p.is_dir() else 'MISSING')}] {p}')",
                ]
            ),
        ],
    )

    write(
        "01_full_pipeline.ipynb",
        [
            md(
                [
                    "# Full pipeline",
                    "",
                    "Same behavior as `main.py` / root `main.ipynb`.",
                    "",
                    "- `FOLDER`: one issue folder name under `Input/`, or `None` for all.",
                    "- `RUN_EVAL`: if True, after converter run `evaluation.py` (Output vs `Input_Eval`).",
                ]
            ),
            code(
                ROOT_RESOLVE.split("\n")
                + [
                    "",
                    "FOLDER = None  # e.g. 'ajil0120no1'",
                    "RUN_EVAL = True",
                ]
            ),
            code(
                [
                    "import logging",
                    "import os",
                    "import sys",
                    "from pathlib import Path",
                    "from typing import Optional",
                    "",
                    "from Combinator.combine_results_v2 import combine_folder as combine_folder_results",
                    "from Converter.yml_manager import process_journal as convert_journal_result",
                    "from CrossRef.extract import process_folder",
                    "from Utilities.app_logging import setup_logging",
                    "from Webscraper.databaseScrape import process as process_database_fallback",
                    "from Webscraper.recursiveScrape import scrape_from_database_url",
                    "from Webscraper.scraper import scrape_from_crossref_result, scrape_without_crossref",
                    "from LLM.ocr_pipeline import run_ocr_pipeline",
                    "from evaluation import evaluationScore",
                ]
            ),
            code(
                [
                    "def wait_for_ocr_pipeline(folder_name, ocr_process):",
                    "    logging.info(",
                    "        'Waiting for OCR pipeline process to finish for folder=%s child_pid=%s',",
                    "        folder_name,",
                    "        ocr_process.pid,",
                    "    )",
                    "    stdout, stderr = ocr_process.communicate()",
                    "    if ocr_process.returncode == 0:",
                    "        logging.info('OCR pipeline completed for folder=%s pid=%s', folder_name, ocr_process.pid)",
                    "    else:",
                    "        logging.error(",
                    "            'OCR pipeline failed for folder=%s pid=%s returncode=%s stderr=%s',",
                    "            folder_name, ocr_process.pid, ocr_process.returncode, stderr.strip(),",
                    "        )",
                    "    if stdout.strip():",
                    "        logging.info('OCR pipeline stdout for folder=%s:\\n%s', folder_name, stdout.strip())",
                    "    if stderr.strip() and ocr_process.returncode == 0:",
                    "        logging.warning('OCR pipeline stderr for folder=%s:\\n%s', folder_name, stderr.strip())",
                ]
            ),
            code(
                [
                    "def run_pipeline(project_root: Path, folder: Optional[str] = None, run_eval: bool = True) -> None:",
                    "    log_file = setup_logging()",
                    "    input_dir = project_root / 'Input'",
                    "    crossref_results_dir = project_root / 'CrossRef' / 'results'",
                    "    webscraper_output_dir = project_root / 'Webscraper' / 'output'",
                    "    webscraper_results_dir = project_root / 'Webscraper' / 'results'",
                    "    process_id = os.getpid()",
                    "    logging.info('Application started with pid=%s', process_id)",
                    "    print(f'Logging to {log_file}')",
                    "    if not input_dir.exists():",
                    "        logging.error('Input folder not found: %s', input_dir)",
                    "        print(f'Input folder not found: {input_dir}')",
                    "        return",
                    "    processed_count = 0",
                    "    folders = sorted(path for path in input_dir.iterdir() if path.is_dir())",
                    "    if folder:",
                    "        target_folder = input_dir / folder",
                    "        if not target_folder.exists() or not target_folder.is_dir():",
                    "            logging.error('Requested folder not found in Input: %s', target_folder)",
                    "            print(f'Requested folder not found in Input: {target_folder}')",
                    "            return",
                    "        folders = [target_folder]",
                    "    for f in folders:",
                    "        logging.info('Dispatching folder=%s main_pid=%s', f.name, process_id)",
                    "        process_folder(f.name, str(f))",
                    "        crossref_result_file = crossref_results_dir / f'{f.name}.json'",
                    "        if crossref_result_file.exists():",
                    "            logging.info('Starting Webscraper for folder=%s using CrossRef result=%s', f.name, crossref_result_file)",
                    "            scrape_from_crossref_result(f.name, str(crossref_result_file), output_dir=str(webscraper_output_dir), results_dir=str(webscraper_results_dir))",
                    "            processed_count += 1",
                    "        else:",
                    "            logging.info('No CrossRef result found for folder=%s; starting databaseScrape fallback', f.name)",
                    "            fallback_result = process_database_fallback(f.name)",
                    "            logging.info('databaseScrape fallback completed for folder=%s status=%s url=%s', f.name, fallback_result.get('status'), fallback_result.get('url'))",
                    "            if fallback_result.get('status') == 'matched':",
                    "                logging.info('Starting recursiveScrape for folder=%s using databaseScrape url=%s', f.name, fallback_result.get('url'))",
                    "                scrape_from_database_url(f.name, fallback_result['url'], output_dir=str(webscraper_output_dir), results_dir=str(webscraper_results_dir))",
                    "                processed_count += 1",
                    "            else:",
                    "                scrape_without_crossref(f.name)",
                    "        print(f'Input Directory: {input_dir}, Folder: {f.name}')",
                    "        ocr_input_dir = os.path.join(input_dir, f.name)",
                    "        print(f'Running OCR pipeline for folder: {ocr_input_dir}')",
                    "        run_ocr_pipeline(ocr_input_dir)",
                    "        logging.info('Starting combinator for folder=%s after OCR wait', f.name)",
                    "        combine_folder_results(f.name)",
                    "        logging.info('Finished combinator for folder=%s', f.name)",
                    "        logging.info('Starting converter for folder=%s after combinator', f.name)",
                    "        convert_output_path = convert_journal_result(f.name)",
                    "        if convert_output_path:",
                    "            logging.info('Finished converter for folder=%s output=%s', f.name, convert_output_path)",
                    "            if run_eval:",
                    "                eval_gt = project_root / 'Input_Eval' / f.name / 'structure.yml'",
                    "                if eval_gt.exists():",
                    "                    try:",
                    "                        logging.info('Starting evaluation for folder=%s', f.name)",
                    "                        evaluationScore(str(Path(convert_output_path).resolve()))",
                    "                    except Exception:",
                    "                        logging.exception('Evaluation failed for folder=%s', f.name)",
                    "                else:",
                    "                    logging.warning('Skipping evaluation: ground truth not found at %s', eval_gt)",
                    "        else:",
                    "            logging.warning('Converter did not generate output for folder=%s', f.name)",
                    "    logging.info('Finished processing %s folder(s)', processed_count)",
                    "    print(f'Finished processing {processed_count} folder(s)')",
                ]
            ),
            code(["run_pipeline(PROJECT_ROOT, folder=FOLDER, run_eval=RUN_EVAL)"]),
        ],
    )

    write(
        "02_evaluation.ipynb",
        [
            md(
                [
                    "# Evaluation (`evaluation.py`)",
                    "",
                    "Scores `Output/<name>.yml` against `Input_Eval/<name>/structure.yml`.",
                    "",
                    "Set `OUTPUT_YML` to a path like `Output/ajil0120no1.yml`.",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "OUTPUT_YML = 'Output/ajil0120no1.yml'  # relative to PROJECT_ROOT",
                    "",
                    "from evaluation import evaluationScore",
                    "",
                    "evaluationScore(str(PROJECT_ROOT / OUTPUT_YML))",
                ]
            ),
        ],
    )

    write(
        "03_evaluation_compare.ipynb",
        [
            md(
                [
                    "# Compare evaluation runs (`evaluation_compare.py`)",
                    "",
                    "Either set **two JSON paths**, or set `USE_LATEST = True` with `JOURNAL` to compare the two newest runs under `Evaluation/<journal>/`.",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "USE_LATEST = True",
                    "JOURNAL = 'ajil0120no1'",
                    "RUN1_JSON = None  # e.g. 'Evaluation/ajil0120no1/ajil0120no1_20260101_120000.json'",
                    "RUN2_JSON = None",
                    "",
                    "from evaluation_compare import compare, get_latest_runs",
                    "",
                    "if USE_LATEST:",
                    "    p1, p2 = get_latest_runs(JOURNAL, PROJECT_ROOT)",
                    "    print(p1, p2)",
                    "    compare(p1, p2)",
                    "else:",
                    "    assert RUN1_JSON and RUN2_JSON",
                    "    compare(str(PROJECT_ROOT / RUN1_JSON), str(PROJECT_ROOT / RUN2_JSON))",
                ]
            ),
        ],
    )

    write(
        "04_stage_crossref.ipynb",
        [
            md(["# Stage: CrossRef", "", "Runs `process_folder` for one issue under `Input/`."]),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "FOLDER = 'ajil0120no1'",
                    "",
                    "from CrossRef.extract import process_folder",
                    "",
                    "inp = PROJECT_ROOT / 'Input' / FOLDER",
                    "process_folder(FOLDER, str(inp))",
                ]
            ),
        ],
    )

    write(
        "05_stage_llm_ocr.ipynb",
        [
            md(
                [
                    "# Stage: LLM OCR pipeline (`LLM/ocr_pipeline.py`)",
                    "",
                    "- `MODE = 'one'`: set `JOURNAL` (folder under `Input/`).",
                    "- `MODE = 'all'`: runs `run_all_journals` on the whole `Input/` tree.",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "MODE = 'one'  # 'one' | 'all'",
                    "JOURNAL = 'ajil0120no1'",
                    "",
                    "from LLM.ocr_pipeline import run_ocr_pipeline, run_all_journals",
                    "",
                    "if MODE == 'all':",
                    "    run_all_journals(str(PROJECT_ROOT / 'Input'))",
                    "else:",
                    "    run_ocr_pipeline(str(PROJECT_ROOT / 'Input' / JOURNAL))",
                ]
            ),
        ],
    )

    write(
        "06_stage_combinator.ipynb",
        [
            md(["# Stage: Combinator (`Combinator/combine_results_v2.py`)", "", "`combine_folder` merges CrossRef / Webscraper / LLM JSON."]),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "FOLDER = 'ajil0120no1'",
                    "",
                    "from Combinator.combine_results_v2 import combine_folder",
                    "",
                    "combine_folder(FOLDER)",
                ]
            ),
        ],
    )

    write(
        "07_stage_converter_dispatch.ipynb",
        [
            md(
                [
                    "# Stage: Converter dispatch (`Converter/manager.py`)",
                    "",
                    "Chooses `yml_manager` vs `yml_manager1` from `structure.yml` section count. Requires `Converter/` on `sys.path` like the CLI.",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "JOURNAL = 'ajil0120no1'",
                    "KEEP_PROBABLE_MATTER = False",
                    "",
                    "import sys",
                    "conv = PROJECT_ROOT / 'Converter'",
                    "if str(conv) not in sys.path:",
                    "    sys.path.insert(0, str(conv))",
                    "import manager",
                    "manager.dispatch(JOURNAL, keep_probable_matter=KEEP_PROBABLE_MATTER)",
                ]
            ),
        ],
    )

    write(
        "08_validator_yml_compare.ipynb",
        [
            md(["# Validator (`Validator/yml_compare.py`)", "", "Validates `Output/` YML files against `HeinData/After/...` and writes reports under `Validator/results/`."]),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "from Validator.yml_compare import main as validator_main",
                    "",
                    "validator_main()",
                ]
            ),
        ],
    )

    write(
        "09_utilities_archive_outputs.ipynb",
        [
            md(["# Archive outputs (`Utilities/archive_outputs.py`)", "", "Moves pipeline outputs into `Old-outputs/<timestamp>/`."]),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "from Utilities.archive_outputs import main as archive_main",
                    "",
                    "archive_main()",
                ]
            ),
        ],
    )

    write(
        "10_llm_extract_doi.ipynb",
        [
            md(
                [
                    "# Extract DOIs (`LLM/extract_doi.py`)",
                    "",
                    "This script uses `from source.ocr import ...`; run from the `LLM/` directory (same as the CLI).",
                    "",
                    "- `MODE = 'one'`: journal folder under `LLM/Data/`.",
                    "- `MODE = 'all'`: `run_all_journals_dois('Data')` relative to `LLM/`.",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "import os",
                    "import sys",
                    "",
                    "MODE = 'one'",
                    "JOURNAL = 'ajil0120no1'",
                    "",
                    "LLM_DIR = PROJECT_ROOT / 'LLM'",
                    "os.chdir(LLM_DIR)",
                    "if str(LLM_DIR) not in sys.path:",
                    "    sys.path.insert(0, str(LLM_DIR))",
                    "from extract_doi import extract_dois, run_all_journals_dois",
                    "",
                    "if MODE == 'all':",
                    "    run_all_journals_dois('Data')",
                    "else:",
                    "    extract_dois(os.path.join('Data', JOURNAL))",
                ]
            ),
        ],
    )

    write(
        "11_webscraper_database_scrape.ipynb",
        [
            md(["# Webscraper: database lookup (`Webscraper/databaseScrape.py`)", "", "Interactive-style: resolves Hein-style folder name to a URL via configured journals."]),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "from Utilities.app_logging import setup_logging",
                    "from Webscraper.databaseScrape import process",
                    "",
                    "setup_logging()",
                    "JOURNAL_KEY = 'mijoeqv0015no1'",
                    "process(JOURNAL_KEY)",
                ]
            ),
        ],
    )

    write(
        "12_webscraper_full_crawl_demo.ipynb",
        [
            md(
                [
                    "# Webscraper: full crawl demo (`Webscraper/scraper.py` __main__)",
                    "",
                    "Runs the same loop as the module’s CLI block over `JOURNALS` (can be long / network-heavy).",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "import os",
                    "import json",
                    "from urllib.parse import urlparse",
                    "",
                    "os.chdir(PROJECT_ROOT / 'Webscraper')",
                    "from Webscraper.scraper import JOURNALS, crawl, is_domain_only, write_raw_output, write_results_output",
                    "",
                    "os.makedirs('output', exist_ok=True)",
                    "for journal_name, start_url in list(JOURNALS.items())[:1]:",
                    "    print(journal_name, start_url)",
                    "    visited, articles = set(), {}",
                    "    parsed = urlparse(start_url)",
                    "    domain = parsed.netloc",
                    "    base_path = None if is_domain_only(start_url) else parsed.path",
                    "    crawl(start_url, domain, base_path, journal_name, visited, articles)",
                    "    out = write_raw_output(journal_name, articles)",
                    "    print('Saved', out)",
                ]
            ),
        ],
    )

    write(
        "13_combinator_v1_batch.ipynb",
        [
            md(
                [
                    "# Legacy combinator batch (`Combinator/combine_results.py`)",
                    "",
                    "Runs `main()` from the older combiner: discovers folders and runs `combine_folder` for each.",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "from Combinator.combine_results import main as combinator_v1_main",
                    "",
                    "combinator_v1_main()",
                ]
            ),
        ],
    )

    write(
        "14_evaluation_subscores.ipynb",
        [
            md(
                [
                    "# Evaluation sub-scores only (optional)",
                    "",
                    "Runs the same logic as `EvaluationScript/evaluation_*` CLI helpers: load `Output/<name>.yml` and `Input/<name>/structure.yml` (note: different from top-level `evaluation.py` which uses `Input_Eval`).",
                ]
            ),
            code(ROOT_RESOLVE.split("\n")),
            code(
                [
                    "OUTPUT_YML = 'Output/ajil0120no1.yml'",
                    "",
                    "import yaml",
                    "from pathlib import Path",
                    "from EvaluationScript.evaluation_general import score_general",
                    "from EvaluationScript.evaluation_section import score_sections, print_section_report",
                    "from EvaluationScript.evaluation_page import score_pages, print_page_report",
                    "",
                    "out = PROJECT_ROOT / OUTPUT_YML",
                    "folder_name = out.stem",
                    "structure_path = PROJECT_ROOT / 'Input' / folder_name / 'structure.yml'",
                    "with open(out, encoding='utf-8') as f:",
                    "    candidate = yaml.safe_load(f)",
                    "with open(structure_path, encoding='utf-8') as f:",
                    "    ground_truth = yaml.safe_load(f)",
                    "rg, _ = score_general(candidate, ground_truth)",
                    "rs, cj = score_sections(candidate, ground_truth)",
                    "rp, cjp = score_pages(candidate, ground_truth)",
                    "print('general', rg['general_score'])",
                    "print_section_report(rs, cj)",
                    "print_page_report(rp, cjp)",
                ]
            ),
        ],
    )


if __name__ == '__main__':
    main()
