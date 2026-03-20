import os
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image


def configure_tesseract():
    env_tesseract = os.getenv("TESSERACT_CMD", "").strip()
    env_tessdata = os.getenv("TESSDATA_PREFIX", "").strip()
    candidate_paths = []

    if env_tesseract:
        candidate_paths.append(Path(env_tesseract))

    candidate_paths.extend(
        [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
    )

    for candidate in candidate_paths:
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            tessdata_dir = candidate.parent / "tessdata"
            expected_traineddata = tessdata_dir / "eng.traineddata"
            env_tessdata_path = Path(env_tessdata) if env_tessdata else None
            env_traineddata = env_tessdata_path / "eng.traineddata" if env_tessdata_path else None

            if tessdata_dir.exists() and expected_traineddata.exists():
                if not env_tessdata_path or not env_traineddata.exists():
                    os.environ["TESSDATA_PREFIX"] = str(tessdata_dir) + os.sep
                    print(f"Using TESSDATA_PREFIX: {os.environ['TESSDATA_PREFIX']}")
                else:
                    os.environ["TESSDATA_PREFIX"] = str(env_tessdata_path) + os.sep
                    print(f"Using TESSDATA_PREFIX from environment: {os.environ['TESSDATA_PREFIX']}")
            print(f"Using Tesseract executable: {candidate}")
            return str(candidate)

    current_cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
    if env_tessdata:
        print(f"Using TESSDATA_PREFIX from environment: {env_tessdata}")
    print(f"Using Tesseract executable from PATH: {current_cmd}")
    return current_cmd


configure_tesseract()

def extract_text(image_input, preprocess=False):
    image_obj = None

    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            return ""
        if preprocess:
            img = cv2.imread(image_input)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, img_processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            image_obj = Image.fromarray(img_processed)
        else:
            image_obj = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        if preprocess:
            rgb_image = image_input.convert('RGB')
            open_cv_image = cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
            _, img_processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            image_obj = Image.fromarray(img_processed)
        else:
            image_obj = image_input

    if image_obj:
        custom_config = r'--oem 3 --psm 6'
        return pytesseract.image_to_string(image_obj, config=custom_config)
    return ""

if __name__ == "__main__":

    # Testing code for OCR extraction:
    directory_sample = "Data/ajil0120no1/png/0001.png"
    ocr_output = extract_text(directory_sample, preprocess=True)
    print(ocr_output)
