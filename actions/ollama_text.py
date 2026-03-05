import json
from dataclasses import dataclass

import requests


OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MODEL_ID = "llama3:8b"


@dataclass
class TextResponse:
    text: str


class OllamaTextModel:
    def __init__(self, model_name: str = MODEL_ID):
        self.model_name = model_name or MODEL_ID

    def generate_content(self, prompt):
        if isinstance(prompt, list):
            prompt_text = "\n".join(str(item) for item in prompt if isinstance(item, str))
        else:
            prompt_text = str(prompt)
        return TextResponse(text=_chat(prompt_text, self.model_name))


def _chat(prompt: str, model_name: str = MODEL_ID) -> str:
    payload = {
        "model": model_name or MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content", "").strip()
