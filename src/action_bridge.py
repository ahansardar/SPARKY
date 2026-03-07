import importlib
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any


if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACTIONS_DIR = PROJECT_ROOT / "actions"

# action_name -> (module_file, function_name)
ACTION_MAP = {
    "browser_control": ("browser_control.py", "browser_control"),
    "cmd_control": ("cmd_control.py", "cmd_control"),
    "code_helper": ("code_helper.py", "code_helper"),
    "computer_control": ("computer_control.py", "computer_control"),
    "computer_settings": ("computer_settings.py", "computer_settings"),
    "desktop": ("desktop.py", "desktop_control"),
    "desktop_control": ("desktop.py", "desktop_control"),
    "dev_agent": ("dev_agent.py", "dev_agent"),
    "file_controller": ("file_controller.py", "file_controller"),
    "flight_finder": ("flight_finder.py", "flight_finder"),
    "open_app": ("open_app.py", "open_app"),
    "pdf_summarizer": ("pdf_summarizer.py", "pdf_summarizer"),
    "reminder": ("reminder.py", "reminder"),
    "screen_process": ("screen_processor.py", "screen_process"),
    "screen_processor": ("screen_processor.py", "screen_process"),
    "send_message": ("send_message.py", "send_message"),
    "weather_report": ("weather_report.py", "weather_action"),
    "web_search": ("web_search.py", "web_search"),
    "youtube_video": ("youtube_video.py", "youtube_video"),
}

DISABLED_ACTIONS = {"web_search", "browser_control"}

SPECIAL_ACTIONS = {
    "agent_execute",
    "task_submit",
    "task_status",
    "task_cancel",
    "task_list",
    "memory_get",
    "memory_update",
    "memory_prompt",
}


def _actions_dir() -> Path:
    value = os.getenv("SPARKY_ACTIONS_DIR")
    if value:
        return Path(value)
    return DEFAULT_ACTIONS_DIR


def list_actions() -> list[str]:
    return sorted((set(ACTION_MAP.keys()) - DISABLED_ACTIONS) | SPECIAL_ACTIONS)


def _ensure_project_root_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _load_callable(action_name: str):
    if action_name not in ACTION_MAP:
        raise ValueError(f"Unknown action '{action_name}'.")

    module_file, fn_name = ACTION_MAP[action_name]
    actions_root = _actions_dir()
    parent_dir = str(actions_root.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    module_name = f"actions.{Path(module_file).stem}"
    module_path = _actions_dir() / module_file
    try:
        # Prefer bundled/importable module first (works in frozen builds without .py files on disk).
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Fall back to loading from a file only when the action module itself is missing.
        missing_name = getattr(exc, "name", "") or ""
        if missing_name != module_name:
            raise
        if not module_path.exists():
            raise FileNotFoundError(f"Action module not found: {module_path}")
        spec = importlib.util.spec_from_file_location(f"sparky_ext_{action_name}", str(module_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    fn = getattr(module, fn_name, None)
    if fn is None or not callable(fn):
        raise AttributeError(f"Callable '{fn_name}' not found in {module_path}")
    return fn


def _normalize_priority(priority: str):
    from agent.task_queue import TaskPriority

    value = (priority or "normal").strip().lower()
    if value == "high":
        return TaskPriority.HIGH
    if value == "low":
        return TaskPriority.LOW
    return TaskPriority.NORMAL


def _run_special_action(action_name: str, parameters: dict[str, Any]) -> Any:
    _ensure_project_root_on_path()

    if action_name == "agent_execute":
        from agent.executor import AgentExecutor

        goal = str(parameters.get("goal", "")).strip()
        if not goal:
            raise ValueError("agent_execute requires 'goal'.")
        return AgentExecutor().execute(goal=goal)

    if action_name == "task_submit":
        from agent.task_queue import get_queue

        goal = str(parameters.get("goal", "")).strip()
        if not goal:
            raise ValueError("task_submit requires 'goal'.")
        priority = _normalize_priority(str(parameters.get("priority", "normal")))
        task_id = get_queue().submit(goal=goal, priority=priority)
        return {"task_id": task_id, "status": "queued"}

    if action_name == "task_status":
        from agent.task_queue import get_queue

        task_id = str(parameters.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("task_status requires 'task_id'.")
        status = get_queue().get_status(task_id)
        if status is None:
            return {"task_id": task_id, "status": "not_found"}
        return status

    if action_name == "task_cancel":
        from agent.task_queue import get_queue

        task_id = str(parameters.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("task_cancel requires 'task_id'.")
        ok = get_queue().cancel(task_id)
        return {"task_id": task_id, "cancelled": ok}

    if action_name == "task_list":
        from agent.task_queue import get_queue

        return get_queue().get_all_statuses()

    if action_name == "memory_get":
        from memory.memory_manager import load_memory

        return load_memory()

    if action_name == "memory_update":
        from memory.memory_manager import update_memory

        payload = parameters.get("memory_update")
        if not isinstance(payload, dict):
            raise ValueError("memory_update requires 'memory_update' as a JSON object.")
        return update_memory(payload)

    if action_name == "memory_prompt":
        from memory.memory_manager import load_memory, format_memory_for_prompt

        return format_memory_for_prompt(load_memory())

    raise ValueError(f"Unknown special action '{action_name}'.")


def run_action(action_name: str, parameters: dict[str, Any] | None = None) -> str:
    params = parameters or {}
    if action_name in DISABLED_ACTIONS:
        return "This action is disabled in this build."

    if action_name in SPECIAL_ACTIONS:
        result = _run_special_action(action_name, params)
        if result is None:
            return "Action completed."
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=True, default=str, indent=2)

    fn = _load_callable(action_name)
    signature = inspect.signature(fn)
    kwargs: dict[str, Any] = {}

    if "parameters" in signature.parameters:
        kwargs["parameters"] = params
    if "response" in signature.parameters:
        kwargs["response"] = None
    if "player" in signature.parameters:
        kwargs["player"] = None
    if "session_memory" in signature.parameters:
        kwargs["session_memory"] = None
    if "speak" in signature.parameters:
        kwargs["speak"] = None

    result = fn(**kwargs)
    if result is None:
        return "Action completed."
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=True, default=str, indent=2)
