import base64
import io
import json
import os
import sys

import polars as pl
import requests
from dotenv import load_dotenv
from loguru import logger
from PIL import Image

load_dotenv()

logger.remove()
logger.add(sys.stderr, level="DEBUG")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("API_KEY is not set in the environment variables.")


def encode_resized_image_to_base64(image_path, max_size=(512, 512)) -> str:
    with Image.open(image_path) as img:
        img.thumbnail(max_size)  # Resize in-place, preserving aspect ratio
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")  # or "JPEG"
        return base64.b64encode(buffered.getvalue()).decode("utf-8")


def infer_model(prompt: str, image_path: str = None) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}

    parts = [{"text": prompt}]

    if image_path:
        logger.debug(image_path)
        base64_image = encode_resized_image_to_base64(image_path)
        parts.append(
            {
                "inlineData": {
                    "mimeType": "image/png",  # match format from `save(...)`
                    "data": base64_image,
                }
            }
        )

    data = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.5,
        },
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        logger.debug(response.json())
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None


def get_prediction_result(image_path) -> pl.DataFrame | None:
    nl = """
        INSTRUCTION:
        - Get the all any products name from the image
        - Validate the products name if it is a valid product name
        - Translate the prducts name to ENGLISH and INDONESIAN.
        - Make the possible word combination with maximing word 4 for keywords for searching the product
        - Sort it by the most relevant unique keywords to avoid too general result.
        - return all the product information in a list of json.
        EXAMPLE OUTPUT:
        EXAMPLE 1:
        ```json
        [{\"name_original\": \"Laziza Chicken Recipe & Seasoning\", \"name_indonesian\":  \"Laziza Chicken Resep & Bumbu\", \"name_english\": \"Laziza Chicken Recipe & Seasoning\", \"keywords\": [\"Laziza Chicken\", \"Chicken Receipe\", \"Seasoning\", \"Bumbu\"], \"count\": 2}]
        ```
        EXAMPLE 2:
        ```json
        [
        {\"name_original\": \"Laziza Chicken Recipe & Seasoning\", \"name_indonesian\":  \"Laziza Chicken Resep & Bumbu\", \"name_english\": \"Laziza Chicken Recipe & Seasoning\", \"keywords\": [\"Laziza Chicken\", \"Chicken Receipe\", \"Seasoning\", \"Bumbu\"], \"count\": 2},
        {\"name_original\": \"masako rasa ayam\", \"name_indonesian\":  \"masako rasa ayam\", \"name_english\": \"masako rasa ayam\", \"keywords\": [\"masako\", \"masako rasa ayam\", \"masako rasa\", \"masako rasa ayam\"], \"count\": 1}
        ]
        ```

        DONT ADD ANY OTHER TEXT, JUST RETURN THE JSON
        ALWAYS SURROUND THE JSON WITH CODE BLOCK
        USE ONLY LOWERCASE LETTERS
        DONT HALLUCINATE! BE PRECISE!
    """

    try:
        logger.debug(image_path)
        response = infer_model(prompt=nl, image_path=image_path)
        logger.debug(f"Response: {response}")
        response_content = (
            response.get("candidates")[0].get("content").get("parts")[0].get("text")
        )
        response_content = _post_process_response(response_content)
        return response_content
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None


def _post_process_response(response: str) -> pl.DataFrame:
    """
    Post-process the response to extract the relevant information.
    """
    try:
        logger.debug(response)
        json_string = response.strip("```json").strip("```").strip()
        contents_json = json.loads(json_string)
        logger.debug(contents_json)
        df = pl.DataFrame(contents_json)
        logger.debug(df)
        return df

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return pl.DataFrame()


if __name__ == "__main__":
    # image_path = "/home/hattajr/lab/ikmimart/.trash/test_images/belinis2.jpg"
    image_paths = [
        ".trash/images/2000000203119.png",
        ".trash/images/5028217001530.png",
        ".trash/images/5760725114349.png",
        ".trash/images/6191315500034.png",
    ]

    for image_path in image_paths:
        print(f"Processing image: {image_path}")
        result = get_prediction_result(image_path)
        print(result)
