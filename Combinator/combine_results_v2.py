import os
import json
from pathlib import Path
from difflib import SequenceMatcher

from merge_sections import merge_sections

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 

# Define source directories for each type of result
SOURCE_FILES = {
    "crossref": PROJECT_ROOT / "CrossRef" / "results",
    "webscraper": PROJECT_ROOT / "Webscraper" / "results",
    "llm": PROJECT_ROOT / "LLM" / "results",
}

# Priority order: first has highest priority
SOURCE_PRIORITY = ["crossref", "webscraper", "llm"]

# Loading JSON file utility
def load_json(filepath):
    """Load and return a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

# Load data from each source for the given journal, if available. Handle errors gracefully.
def load_sources(folder_name):
    """
    Loads JSON from each source folder for the given journal.
    
    Looks for any JSON file containing the folder_name in each source directory.
    
    Args:
        folder_name: Journal folder name (e.g. "ajil0120no1")
    
    Returns:
        dict: {source_name: data} for each source that has results
    """
    sources = {}

    for source_name, source_path in SOURCE_FILES.items():
        if not source_path.exists():
            print(f"  ✗ {source_name}: folder not found ({source_path})")
            continue

        # Find JSON files matching the folder name
        matched_files = [
            f for f in source_path.iterdir()
            if f.suffix == ".json" and folder_name in f.name
        ]

        if not matched_files:
            print(f"  ✗ {source_name}: no results for '{folder_name}'")
            continue

        # If multiple matches, take the most recent (alphabetically last)
        matched_files.sort()
        selected = matched_files[-1]

        try:
            data = load_json(selected)
            sources[source_name] = data
            print(f"  ✓ {source_name}: loaded {selected.name}")
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ✗ {source_name}: failed to load {selected.name} — {e}")

    return sources

# Create output template 
def create_output_template(folder_name):
    """Creates an empty output JSON structure."""
    return {
        "journalName": "", 
        "title": "",
        "volume": "",
        "date": "",
        "pages": [],
        "sections": {}
    }

# Save combined results 
def save_combined(folder_name, combined_data):
    """Saves the combined JSON to Combinator/results/."""
    output_dir = PROJECT_ROOT / "Combinator" / "results"
    output_dir.mkdir(exist_ok=True)

    output_filepath = output_dir / f"{folder_name}.json"

    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)

    print(f"\n  Output saved to: {output_filepath}")
    return output_filepath

# Merge meta data 
def merge_metadata(sources):
    """
    Merges top-level metadata fields (title, volume, date) from all sources.
    Takes the first non-empty value by priority order.
    """
    result = {
        "journalName": "", 
        "title": "",
        "volume": "",
        "date": ""
    }

    for field in result:
        for source in SOURCE_PRIORITY:
            if source not in sources:
                continue
            value = sources[source].get(field, "")
            if value:
                result[field] = value
                print(f"    {field}: \"{value}\" (from {source})")
                break

    return result


def combine_folder(folder_name):
    print(f"\n{'='*60}")
    print(f"Combining results for: {folder_name}")
    print(f"{'='*60}\n") 

    # Load all available sources
    sources = load_sources(folder_name)

    if not sources:
        print(f"\n  ⚠ No sources found for '{folder_name}'")
        return None

    print(f"\n  Loaded {len(sources)} source(s): {', '.join(sources.keys())}")

    # Initialize combined data
    combined_data = create_output_template(folder_name)

    # Combine logic STARTS here (not implemented in this snippet)

    # Merge top-level metadata
    print("\n  Merging metadata...") 
    metadata = merge_metadata(sources)
    combined_data["journalName"] = metadata["journalName"]
    combined_data["title"] = metadata["title"]
    combined_data["volume"] = metadata["volume"]
    combined_data["date"] = metadata["date"]

    # Merge sections
    print("\n  Merging sections...")
    combined_data["sections"] = merge_sections(sources) 


    # Combine logic ENDS

    # Save combined results
    # save_combined(folder_name, combined_data) 

    print(json.dumps(combined_data, indent=2, ensure_ascii=False))  # For demonstration

    return combined_data 


if __name__ == "__main__":
    # combine_folder("ajil0120no1") 

    journals = [
        "ajil0120no1",
        "blj0143no1",
        "direlaw0021",
        "geojlap0023no1",
        "gvnanlj0039no1",
        "intsocwk0069no1",
        "mijoeqv0015no1",
        "modlr0089no1",
        "polic0049no1",
        "rvadctoao0030",
    ]

    for journal in journals:
        combine_folder(journal)