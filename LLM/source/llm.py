import json
import re
import base64
from ollama import chat  

model_name = "qwen3.5:9b" 
safe_model_name = re.sub(r"[^A-Za-z0-9._-]+", "_", model_name)

from openai import OpenAI 
import os 

client = OpenAI(
    api_key= "tgp_v1_ZE17Dd70YCHDqkfpkIbF3jndQ_MoG0jdt4dRRLzrPQE",
    base_url="https://api.together.xyz/v1"
)


def _call_llm(system_prompt, user_content, image_path=None):
    """
    Internal helper to call the LLM and return the raw response string.
    Optionally accepts an image_path to include as vision input.
    """
    user_message = {"role": "user", "content": user_content}

    # Add image if provided
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            b64_image = base64.b64encode(img_file.read()).decode("utf-8")
        user_message["content"] = [
            {"type": "text",      "text": user_content},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
        ]

    response = client.chat.completions.create(
        model="Qwen/Qwen3-Next-80B-A3B-Instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            user_message
        ]
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    return raw

    
# def _call_llm(system_prompt, user_content, image_path=None): 
#     """
#     Internal helper to call the LLM and return the raw response string.
#     """

#     add_instructions = "If you dont know then dont hallucinate, just say null or None. Returning anything other than valid JSON will crash the pipeline.\n\n" 

#     response = client.chat.completions.create( 
#         # model= "google/gemma-3n-E4B-it", 
#         model= "Qwen/Qwen3-Next-80B-A3B-Instruct", 
#         messages=[
#             # {"role": "system", "content": add_instructions + system_prompt},
#             {"role": "system", "content": system_prompt}, 
#             {"role": "user", "content": user_content}
#         ]
#     )

#     raw =  response.choices[0].message.content.strip()

#     # Clean up markdown code fences if present 
#     if raw.startswith("```"):
#         raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
#         raw = raw.rsplit("```", 1)[0]
#         raw = raw.strip()

#     return raw 


# def _call_llm(system_prompt, user_content):
#     """
#     Internal helper to call the LLM and return the raw response string.
#     """
#     response = chat(
#         model=model_name,
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_content}
#         ]
#     )

#     raw = response.message.content.strip()

#     # Clean up markdown code fences if present 
#     if raw.startswith("```"):
#         raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
#         raw = raw.rsplit("```", 1)[0]
#         raw = raw.strip()

#     return raw  

def is_new_article(ocr_text, image_path=None):
    """
    Asks LLM if this page is the start of a new article.

    Returns:
        bool: True if new article, False otherwise
    """

    system_prompt = (
        "You are part of a development pipeline. "
        "Returning anything other than YES or NO will crash the pipeline.\n\n"
        "TASK: Is this the FIRST page of a new article in a journal?\n\n"
        "A first page of a new article MUST have:\n"
        "  - An article title prominently displayed\n"
        "  - Author name(s) below the title\n"
        "  - The beginning of an abstract, introduction, or body text\n\n"
        "A first page of a new article OFTEN has:\n"
        "  - A DOI or footnote with article metadata\n"
        "  - An institutional affiliation for the authors\n\n"
        "This is NOT a first page of an article:\n"
        "  - A title page or front matter with editorial board, publisher info, or copyright notices\n"
        "  - A table of contents or index page\n"
        "  - A continuation of text with no new title/author at the top\n"
        "  - A blank, advertisement, or subscription page\n\n" 
        "IMPORTANT: A page must have BOTH a title AND author name(s) to be a first page.\n\n"
        "RULES:\n"
        "  - Respond with ONLY the word YES or NO\n" 
        "  - Do NOT explain or add any other text\n" 
    )

    raw = _call_llm(
        system_prompt,
        f"PAGE TEXT:\n-----------------\n{ocr_text}\n-----------------\n",
        image_path=image_path
    )

    return raw.strip().upper().startswith("YES") 

def extract_article_fields(ocr_text, image_path=None):
    """
    Extract article title and authors from article OCR text in a single LLM call.

    Args:
        ocr_text: The OCR text from article pages.

    Returns:
        (dict, str): (parsed result dict, raw LLM response)
    """

    system_prompt = (
        "You are part of a development pipeline. "
        "Returning anything other than valid JSON will crash the pipeline.\n\n"
        "TASK: Extract the article title and authors from the text below.\n\n"
        "RULES:\n"
        "  - Return ONLY a JSON object with keys: title, authors\n"
        "  - title: The full article title as a string\n"
        "  - authors: A list of author names, each as a string\n"
        "  - Use null for any field you cannot find\n"
        "  - Do NOT include journal name, volume, or issue as the title\n"
        "  - Do NOT wrap in markdown code fences or add any explanation\n"
        "  - Output must be parseable by json.loads() directly\n\n"
        "EXAMPLE OUTPUT:\n"
        '{"title": "The Rise and Fall of International Law", "authors": ["John Smith", "Jane Doe"]}\n'
    )

    raw = _call_llm(
        system_prompt,
        f"ARTICLE TEXT:\n-----------------\n{ocr_text}\n-----------------\nJSON Output:\n",
        image_path=image_path
    )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"title": None, "authors": None}

    return result, raw

def extract_metadata_fields(ocr_text, pending_fields, image_path=None):
    """
    Extract multiple metadata fields in a single LLM call.

    Args:
        ocr_text: The OCR text from a journal page.
        pending_fields: dict of fields still needed, e.g.
            {
                "volume": "The volume number (e.g. \"89\")",
                "date": "The publication date (e.g. \"January 2026\")",
                "title": "The full journal title (e.g. \"The Modern Law Review\")",
                "issue_number": "The issue number (e.g. \"1\")"
            }

    Returns:
        (dict, str): (parsed result dict, raw LLM response)
    """

    # Build the fields description dynamically from pending_fields
    fields_list = "\n".join(
        f"  - {key}: {desc}" for key, desc in pending_fields.items() 
    )

    # Build example output with only the pending keys 
    example = {key: "<value>" for key in pending_fields}
    example_str = json.dumps(example)

    system_prompt = (
        "You are part of a development pipeline. "
        "Returning anything other than valid JSON will crash the pipeline.\n\n"
        "TASK: Extract the following metadata from the journal text below:\n"
        f"{fields_list}\n\n"
        "RULES:\n"
        f" - Return ONLY a JSON object with these keys: {', '.join(pending_fields.keys())}\n"
        "  - Use null for any field you cannot find\n"
        "  - Do NOT include any keys other than the ones listed above\n"
        "  - Do NOT wrap the JSON in markdown code fences or add any explanation\n"
        "  - Output must be parseable by json.loads() directly\n\n" 
        "EXAMPLE OUTPUT:\n"
        f"{example_str}\n"
    )

    raw = _call_llm(
        system_prompt,
        f"JOURNAL TEXT:\n-----------------\n{ocr_text}\n-----------------\nJSON Output:\n",
        image_path=image_path
    )

    # print("fields_list: " + fields_list)
    # print("\n") 
    # print("example_str: " + example_str)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {key: None for key in pending_fields}

    return result, raw 

def extract_toc_page(ocr_text, image_path=None):  

    # system_prompt = (
    #     f"You are part of a development pipeline." 
    #     f"Returning anything other than 'YES [[Total_Score] = [Score A] + [Score B] + [Score C] + [Score D] + [Score E]]' or 'NO [[Total_Score] = [Score A] + [Score B] + [Score C] + [Score D] + [Score E] = [TOTAL]]' will crash the pipeline.\n\n"
    #     f"TASK: Look at the text below and determine if it is a Table of Contents page from a journal.\n\n"
    #     f"CRITERIA & SCORING: A page is a Table of Contents if it contains ALL of the following: Every criterion can only contribute to the points once:\n" 
    #     f"  - [A][40 Points] IMPORTANT: Page numbers associated with those articles or sections. \n"
    #     f"  - [B][25 Points] Article or section titles \n" 
    #     f"  - [C][15 Points] Author names \n"
    #     f"  - [D][10 Points] In some cases there could be additional information like abstracts or keywords. \n" 
    #     f"  - [E][10 Points] The text is organized in a way that indicates it is a listing of contents. \n\n" 
    #     f"VALID PAGE NUMBERS [A] MUST MEET ALL 4 CONDITIONS:\n"
    #     f"  1. POSITION: At the END of the exact SAME LINE as a title.\n"
    #     f"  2. FORMAT: A number, range, or prefix (e.g., '42', '42-45', 'p.42').\n"
    #     f"  3. SEQUENCE: Must repeat across MULTIPLE lines in STRICTLY ASCENDING ORDER (use range starts; allow 1 OCR error).\n"
    #     f"  4. EXCLUSIONS: Ignore headers, footers, volume numbers, and the document's own page number.\n\n"
    #     f"DECISION RULE: Total_Score >= 70 return 'YES [[Total_Score] = [Score A] + [Score B] + [Score C] + [Score D] + [Score E]]' or else 'NO [[Total_Score] = [Score A] + [Score B] + [Score C] + [Score D] + [Score E] = [TOTAL]]'\n"
    #     f"DECISION RULE: Total_Score >= 70 return 'YES' or else 'NO'\n"  
    #     # f"PAGE TEXT:\n{ocr_text}" 
    # )

    system_prompt = (
        "You are part of a development pipeline. "
        "Returning anything other than YES or NO will crash the pipeline.\n\n"
        "TASK: Is this text a Table of Contents (TOC) page from a journal?\n\n"
        "A Table of Contents page MUST have:\n"
        "  - Multiple article or section titles listed one after another\n"
        "  - Page numbers associated with those titles, typically at the end of the same line\n"
        "  - Page numbers should appear in ascending order across entries\n\n"
        "A Table of Contents page OFTEN has:\n"
        "  - Author names alongside the titles\n"
        "  - Short abstracts or descriptions under each entry\n"
        "  - An organized, repeating structure (title, author, page number)\n\n"
        "IMPORTANT: A continuation of a TOC is still a TOC, even without a heading or title saying 'Table of Contents'.\n\n"
        "NOT a Table of Contents: single articles, title pages, bibliographies, indexes, or header-only pages.\n\n"
        "RULES:\n"
        "  - Page Numbers must always be present\n"
        "  - Respond with ONLY the word YES or NO\n"
        "  - Do NOT explain, justify, or add any other text\n"
        "  - One word only: YES or NO\n"
    )

    raw = _call_llm(
        system_prompt,
        f"JOURNAL TEXT:\n-----------------\n{ocr_text}\n-----------------\nJSON Output:\n",
        image_path=image_path
    )

    return raw

def get_article_page_numbers(ocr_text, image_path=None):  
    system_prompt = (
        "You are part of a development pipeline. "
        "Returning anything other than valid JSON will crash the pipeline.\n\n"
        "TASK: Extract all articles/entries from this Table of Contents text.\n\n"
        "For each entry extract:\n"
        "  - id: The full article title including author name if present\n"
        "  - page: The page number associated with that entry\n\n"
        # "RULES:\n"
        # "  - Return ONLY a JSON array of objects with keys: id, page\n"
        # "  - page must be an integer, not a string\n"
        # "  - Do NOT include journal name, volume, issue number, or section headers as entries\n"
        # "  - Do NOT include abstracts or descriptions in the id, only the title and author\n"
        # "  - Do NOT wrap in markdown code fences or add any explanation\n"
        # "  - Output must be parseable by json.loads() directly\n" 
    )

    raw = _call_llm(
        system_prompt,
        f"JOURNAL TEXT:\n-----------------\n{ocr_text}\n-----------------\nJSON Output:\n",
        image_path=image_path
    )

    return raw

def get_page_number(ocr_text, image_path=None):  
    system_prompt = (
        "You are part of a development pipeline. "
        "Returning anything other than a number will crash the pipeline.\n\n"
        "TASK: What is the printed page number on this page?\n\n"
        "RULES:\n"
        "  - Return ONLY the page number as a single integer\n"
        "  - Look for the number typically at the top or bottom of the page\n"
        "  - Do NOT return file names, line numbers, or any other number\n"
        "  - Do NOT add any explanation or text\n"
        "  - One number only\n"
    )

    raw = _call_llm(
        system_prompt,
        f"PAGE TEXT:\n-----------------\n{ocr_text}\n-----------------\nPage number:\n",
        image_path=image_path
    )

    return raw

def test_ollama(): 
    response = chat(
        model=model_name,
        messages=[
            {
                'role': 'user',
                'content': 'Testing Ollama API with Qwen3.5 model. Please respond with a simple greeting.' 
            }
        ]
    )

    return response.message.content 

if __name__ == "__main__":
    ollama_response = test_ollama() 
    print("Ollama response:", ollama_response)  
