import os
import yaml
import argparse

import yml_manager
import yml_manager1


BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT   = os.path.dirname(BASE_DIR)
RESULTS_DIR    = os.path.join(PROJECT_ROOT, "Combinator", "results")
INPUT_BASE_DIR = os.path.join(PROJECT_ROOT, "Input")
OUTPUT_DIR     = os.path.join(PROJECT_ROOT, "Output")


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_json_files(journal_name=None):
    if not os.path.isdir(RESULTS_DIR):
        raise FileNotFoundError(f"results directory not found: {RESULTS_DIR}")

    if journal_name:
        json_filename = f"{journal_name}.json"
        json_path = os.path.join(RESULTS_DIR, json_filename)
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        return [json_filename]

    return sorted(
        f for f in os.listdir(RESULTS_DIR)
        if f.lower().endswith(".json")
    )


def get_matching_structure_path(journal_name):
    return os.path.join(INPUT_BASE_DIR, journal_name, "structure.yml")


def get_section_count(structure_yml: dict) -> int:
    return len(structure_yml.get("sections", {}))


def dispatch(journal_name: str, keep_probable_matter: bool = False):
    structure_path = get_matching_structure_path(journal_name)

    if not os.path.exists(structure_path):
        print(f"[SKIP] {journal_name} -> structure.yml not found")
        return

    structure_yml = load_yaml(structure_path)
    section_count = get_section_count(structure_yml)

    if section_count == 1:
        print(f"[DISPATCH] {journal_name} -> yml_manager  (sections: {section_count})")
        yml_manager.process_journal(journal_name, keep_probable_matter=keep_probable_matter)
    elif section_count > 1:
        print(f"[DISPATCH] {journal_name} -> yml_manager1 (sections: {section_count})")
        yml_manager1.process_journal(journal_name, keep_probable_matter=keep_probable_matter)
    else:
        print(f"[WARN] {journal_name} has 0 sections in structure.yml — skipping")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", help="Process only one journal, e.g. ajil0120no1")
    parser.add_argument(
        "--keep-probable-matter",
        action="store_true",
        help="Pass --keep-probable-matter through to whichever manager is called",
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        json_files = get_json_files(args.journal)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    if not json_files:
        print(f"[INFO] No JSON files found in {RESULTS_DIR}")
        return

    for json_filename in json_files:
        journal_name = os.path.splitext(json_filename)[0]
        dispatch(journal_name, keep_probable_matter=args.keep_probable_matter)


if __name__ == "__main__":
    main()