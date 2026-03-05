import json
import urllib.request
import urllib.error

try:
    import requests  # type: ignore
except Exception:
    requests = None

OLLAMA_URL = "http://localhost:11434/api/chat"
FORCED_MODEL = "llama3:8b"

def chat_with_model(model_name: str, messages: list, stream: bool = True):
    payload = {
        "model": FORCED_MODEL,
        "messages": messages,
        "stream": stream
    }

    if requests is not None:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            stream=stream,
            timeout=300
        )
        response.raise_for_status()

        if not stream:
            return response.json()["message"]["content"]

        full_reply = ""
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line.decode("utf-8"))
            if "message" in data and "content" in data["message"]:
                chunk = data["message"]["content"]
                print(chunk, end="", flush=True)
                full_reply += chunk
            if data.get("done"):
                break
        print()
        return full_reply

    # Fallback path when requests is unavailable in bundled/runtime env.
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            if not stream:
                data = json.loads(resp.read().decode("utf-8"))
                return data["message"]["content"]

            full_reply = ""
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                data = json.loads(line.decode("utf-8"))
                if "message" in data and "content" in data["message"]:
                    chunk = data["message"]["content"]
                    print(chunk, end="", flush=True)
                    full_reply += chunk
                if data.get("done"):
                    break
            print()
            return full_reply
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
