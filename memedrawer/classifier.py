import base64
import json
import io
import re
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from PIL import Image

# Import configurations
from memedrawer.config import AppConfig

class ClassificationResult(BaseModel):
    board: Optional[str] = Field(
        None, 
        description="4chan board code if the image belongs to a specific board topic (e.g., '/g/' for tech/programming, '/pol/' for politics/news, '/a/' for anime/manga, '/s/' for beautiful women/models, '/v/' for gaming, '/biz/' for business/finance, '/k/' for military/weapons, '/art/' for fine art, '/tg/' for traditional games/Magic: The Gathering). Set to null if it does not fit these board categories."
    )
    primary_folder: str = Field(
        ..., 
        description="The main folder name. For reaction faces, reaction GIFs, and expressions, use 'reaction images'. Otherwise, use descriptive categories like 'technology', 'gaming', 'anime', 'politics', 'cat memes', 'wallpapers', 'art', 'tg', 'miscellaneous'."
    )
    subcategory: Optional[str] = Field(
        None, 
        description="For 'reaction images', use a clear emotion/reaction (e.g. 'happy', 'sad', 'smug', 'angry', 'laughing', 'shocked', 'thinking', 'facepalm'). For other categories, use a descriptive sub-topic (e.g. 'programming' for tech, 'retro' for gaming, a political topic like 'trump' or 'ukraine' for politics, or null if no subcategory makes sense)."
    )
    suggested_filename: str = Field(
        ..., 
        description="A descriptive filename for the image, summarizing its visual content and text. Use lowercase alphanumeric characters and underscores only. Max 40 characters. E.g. 'sad_pepe_crying', 'wojak_brain_expansion', 'maid_blushing'."
    )
    commentary: Optional[str] = Field(
        None,
        description="A cute, short comment from Mimi the maid about this meme/image, written in character as a polite, helper anime maid (referring to the user as 'Master'). Keep it under 15 words. E.g. 'A very funny cat indeed, Master!' or 'Oh dear, this politics meme is quite spicy!'"
    )

CLASSIFICATION_PROMPT = """Analyze this image (meme, image macro, reaction image, or random saved picture) and classify it for sorting.

Classification Rules:
1. Determine if it belongs to a 4chan-like board topic:
   - Tech/Coding/Computers/Hardware -> board: "/g/", primary_folder: "technology"
   - Politics/Current Events/Political figures -> board: "/pol/", primary_folder: "politics". Set the subcategory to a specific, concise topic of the politics/news event (e.g., "trump", "russia", "china", "feminism", "military", "ukraine", etc., as appropriate).
   - Video Games/Gaming/Consoles -> board: "/v/", primary_folder: "gaming"
   - Anime/Manga/Japanese culture/Light novels -> board: "/a/", primary_folder: "anime"
   - Beautiful women/Models/Sexy/Glamour photography -> board: "/s/", primary_folder: "beautiful women"
   - Food/Cooking/Recipes/Meals/Drinks -> board: "/ck/", primary_folder: "cooking"
   - Wallpapers/High-resolution landscapes/Aesthetics -> board: "/wg/", primary_folder: "wallpapers"
   - Fitness/Gym/Bodybuilding/Workouts -> board: "/fit/", primary_folder: "fitness"
   - Comic Books/Cartoons/Western Animation -> board: "/co/", primary_folder: "comics"
   - Business/Finance/Crypto -> board: "/biz/", primary_folder: "finance"
   - Weapons/Military/Gear -> board: "/k/", primary_folder: "military"
   - Movies/TV/Shows -> board: "/tv/", primary_folder: "television"
   - Fine Art/Paintings/Sculptures/Classical art -> board: "/art/", primary_folder: "art"
   - Magic: The Gathering cards -> board: "/tg/", primary_folder: "tg"
   - Otherwise -> board: null

2. If the image is a reaction face, reaction expression, or reaction macro (e.g., crying pepe, laughing anime girl, disappointed guy, facepalm):
   - primary_folder: "reaction images"
   - subcategory: The reaction type, e.g., "happy", "sad", "smug", "angry", "laughing", "shocked", "thinking", "facepalm", "disappointed", "approval", "pointing", "nodding".

3. Suggest a descriptive, clean filename summarizing the image contents (e.g., "sad_pepe_crying_at_screen", "wojak_money_printer", "gigachad_smiling").
   - Use lowercase, numbers, and underscores only.
   - Do NOT include any file extensions in the suggested_filename.
   - Keep it short and descriptive (max 40 chars).
   - Do NOT include the words "meme" or "memes" in the suggested_filename (e.g., use "sad_pepe_crying" instead of "sad_pepe_crying_meme").

4. Provide a cute, short comment from Mimi the maid about this meme/image in 'commentary'. She is a polite but playful anime maid, e.g., referring to the user as 'Master'. Keep it under 15 words.

You MUST respond in JSON matching this schema:
{
  "board": "/g/" or "/pol/" or "/a/" or "/s/" or "/ck/" or "/wg/" or "/fit/" or "/co/" or "/v/" or "/biz/" or "/k/" or "/tv/" or "/art/" or "/tg/" or null,
  "primary_folder": "reaction images" or "technology" or "gaming" or "politics" or "anime" or "beautiful women" or "cooking" or "art" or "tg" etc.,
  "subcategory": "happy" or "sad" or "programming" or "trump" or null etc.,
  "suggested_filename": "lowercase_underscored_name",
  "commentary": "a cute maid comment under 15 words"
}
"""

def prepare_image(image_path: Path, max_size: int = 800) -> tuple[bytes, str]:
    """
    Loads, verifies, and resizes/compresses the image to optimize upload speed
    and LLM processing. Returns the compressed bytes and the MIME type.
    """
    img = Image.open(image_path)
    
    # Identify format and MIME type
    fmt = img.format or "JPEG"
    mime_type = f"image/{fmt.lower()}"
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
        
    # Standardize image modes to RGB/RGBA
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
        
    # Resize keeping aspect ratio
    width, height = img.size
    if max(width, height) > max_size:
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
    # Save to bytes
    out_io = io.BytesIO()
    # Save as JPEG for best compression, or keep PNG/GIF if alpha channel/animation is needed
    save_format = "PNG" if img.mode == "RGBA" else "JPEG"
    img.save(out_io, format=save_format, quality=85)
    return out_io.getvalue(), f"image/{save_format.lower()}"

def clean_json_response(text: str) -> str:
    """Extracts JSON block from markdown code blocks if present."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text

def sanitize_llm_dict(raw_dict: dict) -> dict:
    sanitized = {}
    
    # Lowercase all keys to make lookup case-insensitive
    lower_dict = {str(k).lower(): v for k, v in raw_dict.items()}
    
    # 1. Map board
    board_keys = ("board", "board_code", "boardcode", "board_sorting")
    sanitized["board"] = None
    for bk in board_keys:
        if bk in lower_dict:
            val = lower_dict[bk]
            if val and val != "null" and val != "None":
                sanitized["board"] = str(val).strip()
            break
            
    # 2. Map primary_folder
    folder_keys = ("primary_folder", "primaryfolder", "folder", "category", "primary_category", "primarycategory")
    sanitized["primary_folder"] = "miscellaneous"
    for fk in folder_keys:
        if fk in lower_dict:
            val = lower_dict[fk]
            if val:
                sanitized["primary_folder"] = str(val).strip()
            break
            
    # 3. Map subcategory
    sub_keys = ("subcategory", "sub_category", "subcategory", "topic")
    sanitized["subcategory"] = None
    for sk in sub_keys:
        if sk in lower_dict:
            val = lower_dict[sk]
            if val and val != "null" and val != "None":
                sanitized["subcategory"] = str(val).strip()
            break
            
    # 4. Map suggested_filename
    file_keys = ("suggested_filename", "suggestedfilename", "filename", "name", "suggested_name", "suggestedname")
    sanitized["suggested_filename"] = "unnamed_meme"
    for f_key in file_keys:
        if f_key in lower_dict:
            val = lower_dict[f_key]
            if val:
                sanitized["suggested_filename"] = str(val).strip()
            break
            
    # 5. Map commentary
    comment_keys = ("commentary", "comment", "mimi_comment", "mimi_commentary", "thoughts", "maid_comment", "comment_from_mimi")
    sanitized["commentary"] = None
    for ck in comment_keys:
        if ck in lower_dict:
            val = lower_dict[ck]
            if val and val != "null" and val != "None":
                sanitized["commentary"] = str(val).strip()
            break
            
    return sanitized

class LLMClassifier:
    def __init__(self, config: AppConfig):
        self.config = config

    def classify_image(self, image_path: Path, allowed_subfolders: Optional[dict[str, list[str]]] = None) -> ClassificationResult:
        """Classifies an image using local OpenAI API based on config."""
        try:
            image_bytes, mime_type = prepare_image(image_path)
        except Exception as e:
            raise ValueError(f"Failed to load or process image: {e}")

        return self._classify_openai(image_bytes, mime_type, allowed_subfolders)

    def get_text_completion(self, prompt: str) -> str:
        """Runs a text completion on the configured local OpenAI server."""
        from openai import OpenAI

        api_key = self.config.openai_api_key or "no-key-needed"
        base_url = self.config.openai_base_url
        model_name = self.config.openai_model

        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

        messages = [
            {"role": "user", "content": prompt}
        ]

        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
        )

        return response.choices[0].message.content or ""

    def determine_favorite_meme(self, meme_comments: list[dict[str, str]]) -> str:
        """Determines Mimi's favorite meme from the list of processed memes and comments."""
        if not meme_comments:
            return ""

        prompt = "Here is a list of memes Mimi the maid sorted, along with her thoughts on each:\n\n"
        for idx, item in enumerate(meme_comments):
            prompt += f"{idx + 1}. Filename: {item['filename']} | thoughts: {item['commentary']}\n"
            
        prompt += "\nIdentify which single meme from the list above is Mimi's favorite based on the comments. Respond in character as Mimi (a polite, cute anime maid). Tell 'Master' which filename is your favorite and give a short, cute explanation why in under 20 words."

        try:
            content = self.get_text_completion(prompt)
            return content.strip()
        except Exception as e:
            # Fallback to the first meme
            return f"I liked all of them so much, Master! Especially {meme_comments[0]['filename']}! (Error choosing: {e})"

    def _classify_openai(self, image_bytes: bytes, mime_type: str, allowed_subfolders: Optional[dict[str, list[str]]] = None) -> ClassificationResult:
        from openai import OpenAI

        api_key = self.config.openai_api_key or "no-key-needed"
        base_url = self.config.openai_base_url
        model_name = self.config.openai_model

        # Base64 encode the image bytes for standard OpenAI API format
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

        prompt_text = CLASSIFICATION_PROMPT
        if allowed_subfolders is not None:
            prompt_text += "\nSTRICT SUBFOLDER CONSTRAINT:\n"
            if allowed_subfolders:
                prompt_text += "You MUST restrict the 'subcategory' field for each category/board to ONLY the existing subfolders listed below. If the image does not fit any of the listed subfolders for that category/board, you MUST set 'subcategory' to null.\n"
                for folder, subs in allowed_subfolders.items():
                    prompt_text += f"- For category/board folder '{folder}': allowed subcategories are {', '.join(subs)}\n"
            else:
                prompt_text += "There are no existing subfolders in the destination. You MUST set 'subcategory' to null for all images.\n"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

        # Use JSON mode if possible (some local models / server engines support it)
        # We also pass the response format parameter.
        kwargs = {}
        # Some local servers crash if we specify response_format if they don't support it,
        # so we try to use a safe setup. We'll default to asking for JSON in prompt and parsing it.
        if "api.openai.com" in base_url:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            **kwargs
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Received empty response from OpenAI endpoint.")

        # Try to parse the content as JSON directly or using regex
        parsed_dict = None
        clean_json = clean_json_response(content)
        try:
            parsed_dict = json.loads(clean_json)
        except Exception:
            # Try to extract JSON using regex
            try:
                json_match = re.search(r"\{[\s\S]*\}", clean_json)
                if json_match:
                    parsed_dict = json.loads(json_match.group(0))
            except Exception:
                pass

        if isinstance(parsed_dict, dict):
            try:
                # Sanitize the dictionary keys and fallbacks
                sanitized = sanitize_llm_dict(parsed_dict)
                return ClassificationResult(**sanitized)
            except Exception as parse_error:
                raise ValueError(f"Failed to instantiate ClassificationResult from sanitized dict: {parsed_dict}. Error: {parse_error}")
        else:
            raise ValueError(f"Failed to parse LLM response as a JSON object. Raw response: {content}")
