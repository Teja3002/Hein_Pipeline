import os
import json
from datetime import datetime
import shutil

from source.llm import model_name

def create_metadata_json(base_folder):
    """
    Creates a sample metadata JSON file in the temp folder.
    Other scripts will populate the fields as they process data.
    """
    journal_name = os.path.basename(base_folder)

    metadata = {
        "journalName": journal_name,
        "volume": "",
        "date": "",
        "title": "",
        # "issue_number": "",
        # "issn": "",
        # "eissn": "", 
        "articles": [] 
    }

    json_filename = f"metadata_{model_name}_{journal_name}.json" 
    results_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp") 
    json_filepath = os.path.join(results_path, json_filename) 

    with open(json_filepath, "w", encoding="utf-8") as f: 
        json.dump(metadata, f, indent=4, ensure_ascii=False)

    print(f"Created metadata: {json_filepath}")

    return json_filepath    

def create_ocr_json(base_folder):
    """
    Scans the png folder inside the given base_folder,
    counts all valid image files, and creates an ocrData JSON file.
    """

    folder_path = os.path.join(base_folder, "png")

    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    # Collect valid image files
    valid_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp')
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
    files.sort()

    total_pages = len(files)

    # Extract journal name from the base folder path
    journal_name = os.path.basename(base_folder) 

    # Current date and time
    now = datetime.now()
    date_str = now.strftime("%d-%m-%Y") 
    time_str = now.strftime("%H:%M:%S")
    # datetime_str = now.strftime("%Y%m%d_%H%M%S")

    # Build entries list
    entries = []
    for file_name in files:
        file_path = os.path.join(folder_path, file_name)
        entries.append({
            "fileName": file_name,
            "filePath": os.path.abspath(file_path),
            "ocrText": ""
        })

    structure_path = os.path.join(base_folder, "structure.yml") 

    # Build the JSON structure
    ocr_data = {
        "journalName": journal_name,
        "date": date_str,
        "time": time_str,
        "totalPages": total_pages,
        "structurePath": os.path.abspath(structure_path) if os.path.exists(structure_path) else None,
        "entries": entries
    }

    # Create output JSON file 
    json_filename = f"ocrData_{model_name}_{journal_name}.json"
    results_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp") 
    json_filepath = os.path.join(results_path, json_filename) 

    with open(json_filepath, "w", encoding="utf-8") as f:
        json.dump(ocr_data, f, indent=4, ensure_ascii=False)

    print(f"Created: {json_filepath}") 
    print(f"Total pages found: {total_pages}")

    return json_filepath

def save_metadata_to_output(metadata_filepath, base_folder):
    """
    Copies the metadata JSON from temp/ to output/ with a timestamped name.
    """
    journal_name = os.path.basename(base_folder)
    datetime_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")  
    os.makedirs(output_dir, exist_ok=True)  

    output_filename = f"metadata_{journal_name}_{datetime_str}.json" 
    output_filepath = os.path.join(output_dir, output_filename) 

    shutil.copy2(metadata_filepath, output_filepath)

    print(f"Metadata saved to: {output_filepath}") 
    return output_filepath 

if __name__ == "__main__":

    # Testing code for initializing OCR JSON file: 
    json_filepath = create_ocr_json("Input/ajil0120no1")   
    print(f"JSON file created at: {json_filepath}")