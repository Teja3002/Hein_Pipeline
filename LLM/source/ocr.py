import os
from pathlib import Path
import tempfile
import cv2
import numpy as np
import pytesseract
from PIL import Image
from ollama import chat
import base64



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

def extract_text_tesseract(image_input, preprocess=False):
    image_obj = None

    preprocess = False 

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
        # custom_config = r'--oem 3 --psm 6'
        custom_config = r'--oem 3 --psm 4'
        return pytesseract.image_to_string(image_obj, config=custom_config)
    return ""


OCR_MODEL = "deepseek-ocr"
# from openai import OpenAI

# client = OpenAI(
#     api_key="tgp_v1_ZE17Dd70YCHDqkfpkIbF3jndQ_MoG0jdt4dRRLzrPQE",
#     base_url="https://api.together.xyz/v1"
# )

# # OCR_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"

def extract_text(image_input, preprocess=False) -> str:
    """
    Extracts text from an image using vision LLM via Together API.
    Accepts a file path string or PIL Image object.
    preprocess parameter kept for backward compatibility but unused.
    """

    ocr_output = extract_text_tesseract(image_input, preprocess=preprocess)
    # print(ocr_output) 
    if not ocr_output.strip():
        print("Tesseract OCR returned empty text, falling back.")
        return ocr_output

    # ── Resolve image path ──
    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            return ""
        image_path = image_input

    elif isinstance(image_input, Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_input.save(tmp.name)
            image_path = tmp.name

    else:
        return ""

    # ── Encode image as base64 ──
    with open(image_path, "rb") as img_file:
        b64_image = base64.b64encode(img_file.read()).decode("utf-8")

    print(f"      Running OCR on {image_input} using model {OCR_MODEL}...") 

    # ── Call API ──
    # response = client.chat.completions.create(
    response = chat(
        model=OCR_MODEL,
        messages=[
            {
                "role": "user",
                # "content": [
                #     {"type": "text",      "text": "Extract the text in the image."},
                #     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                # ]
                "content": "Extract the text in the image.",
                "images": [image_input] 
            }
        ]
    )

    return response.message.content.strip() 
    # return response.choices[0].message.content.strip()

if __name__ == "__main__":

    # Testing code for OCR extraction:
    # directory_sample = "../../Input/ajil0120no1/png/0001.png"
    directory_sample = "../../Input/modlr0089no1/png/0003.png"
    ocr_output = extract_text(directory_sample, preprocess=True)
    print(ocr_output)
