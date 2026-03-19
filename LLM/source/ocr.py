import pytesseract
import os 
import cv2 
from PIL import Image 
import numpy as np

def extract_text(image_input, preprocess=False):

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