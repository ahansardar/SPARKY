# actions/web_search.py
# SPARKY - Web Search
# Primary: Ollama synthesis
# Fallback: DuckDuckGo (ddgs)

from actions.ollama_text import OllamaTextModel


def _ollama_search(query: str) -> str:
    model = OllamaTextModel("llama3:8b")
    prompt = (
        "Answer this web-style query clearly and factually. "
        "If you are unsure, say so.\n\n"
        f"Query: {query}"
    )
    response = model.generate_content(prompt)
    text = response.text.strip()
    if not text:
        raise ValueError("Empty response")
    return text


def _ddg_search(query: str, max_results: int = 6) -> list:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                }
            )
    return results


def _format_ddg(query: str, results: list) -> str:
    if not results:
        return f"No results found for: {query}"
    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):
            lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _compare(items: list, aspect: str) -> str:
    query = f"Compare {', '.join(items)} in terms of {aspect}. Give specific facts and data."
    try:
        return _ollama_search(query)
    except Exception as e:
        print(f"[WebSearch] Ollama compare failed: {e}")
        all_results = {}
        for item in items:
            try:
                all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
            except Exception:
                all_results[item] = []
        lines = [f"Comparison - {aspect.upper()}\n{'-' * 40}"]
        for item in items:
            lines.append(f"\n- {item}")
            for r in all_results.get(item, [])[:2]:
                if r.get("snippet"):
                    lines.append(f"  * {r['snippet']}")
        return "\n".join(lines)


def web_search(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query = params.get("query", "").strip()
    mode = params.get("mode", "search").lower()
    items = params.get("items", [])
    aspect = params.get("aspect", "general")

    if not query and not items:
        return "Please provide a search query, sir."

    if items and mode != "compare":
        mode = "compare"

    if player:
        player.write_log(f"[Search] {query or ', '.join(items)}")

    print(f"[WebSearch] Query: {query!r}  Mode: {mode}")

    try:
        if mode == "compare" and items:
            result = _compare(items, aspect)
            return result

        try:
            result = _ollama_search(query)
            return result
        except Exception as e:
            print(f"[WebSearch] Ollama failed ({e}), trying DDG...")
            results = _ddg_search(query)
            result = _format_ddg(query, results)
            return result

    except Exception as e:
        print(f"[WebSearch] Failed: {e}")
        return f"Search failed, sir: {e}"
