"""
Local AI backend for Peeking Cat (talks to Ollama).

What it does
  * streams the answer token by token on a background thread (the UI never freezes)
  * every request has an id, so a late answer can never land in the wrong bubble
  * the request can be cancelled (Esc / closing the bubble) and the model stops
  * finds an installed model by itself if the configured one is missing
  * starts "ollama serve" in the background if Ollama is installed but not running
  * turns markdown (**bold**, # headings, - lists) into clean text for a chat bubble
  * remembers the conversation (it fits a token budget), also across restarts (history_file),
    until reset()
  * TOOLS: the model can really do things in the app: add_todo, add_reminder, start_timer and
    log_study. "Remind me Friday at 8pm to submit the lab" creates the reminder.
    Tools are only offered when the message sounds like one of these jobs (small models call
    tools by mistake when they are always offered). The app runs the tool on the UI thread
    and the cat confirms what it did in plain words (no second model call, so it is fast).

All callbacks and public signals run on the main/UI thread.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot

# Import ollama defensively: with a .pyw file there is no console, so a plain
# "import ollama" failure would make the whole app die silently at startup.
try:
    import ollama
    _IMPORT_ERROR = ""
except Exception as _e:          # not installed in the Python that runs the .pyw
    ollama = None
    _IMPORT_ERROR = str(_e)

DEFAULT_MODEL = "llama3.2"
CONTEXT_TOKENS = 16384           # how much text the model can read at once (bigger = more memory)
MAX_REPLY_TOKENS = 2400          # longest single answer (about 1500+ words); short chat answers stay short
PROMPT_RESERVE = 1200            # room kept for the system prompt and the tool descriptions
HISTORY_TOKENS = CONTEXT_TOKENS - MAX_REPLY_TOKENS - PROMPT_RESERVE   # the chat history must fit in this
REQUEST_TIMEOUT = 180            # seconds to wait for the next piece of an answer (cold model load can be slow)
KEEP_ALIVE = "30m"               # keep the model in memory so the next answer starts fast
SERVER_WAIT_SECONDS = 20         # how long to wait for a freshly started Ollama server
TOOL_WAIT_SECONDS = 15           # how long the worker waits for the app to run a tool


# ----------------------------------------------------------------------
# tools the model may call (the app supplies the code that runs them)
# ----------------------------------------------------------------------
def _tool(name, description, props, required):
    return {"type": "function",
            "function": {"name": name, "description": description,
                         "parameters": {"type": "object", "properties": props, "required": required}}}


TOOL_SPECS = {
    "add_reminder": _tool(
        "add_reminder",
        "Create a reminder. The cat will pop up and say the message at that time.",
        {"message": {"type": "string", "description": "What to remind the user about, e.g. 'submit the lab report'"},
         "when": {"type": "string",
                  "description": "When, in the user's own words: 'in 20 minutes', 'at 5pm', 'tomorrow at 9', "
                                 "'friday at 8pm', 'every weekday at 9:30', 'every 45 minutes'"}},
        ["message", "when"]),
    "add_todo": _tool(
        "add_todo",
        "Add a task to the user's to-do list.",
        {"text": {"type": "string", "description": "The task, e.g. 'buy printer ink'"},
         "due": {"type": "string",
                 "description": "Optional due day: 'today', 'tomorrow', 'fri', 'in 3 days' or '2026-11-05'"}},
        ["text"]),
    "start_timer": _tool(
        "start_timer",
        "Start a countdown timer. The cat says when the time is up.",
        {"minutes": {"type": "integer", "description": "Length of the timer in minutes (1 to 1440)"}},
        ["minutes"]),
    "log_study": _tool(
        "log_study",
        "Write study time into the study tracker.",
        {"subject": {"type": "string", "description": "The subject, e.g. 'Physics'"},
         "minutes": {"type": "integer", "description": "How many minutes were studied"}},
        ["subject", "minutes"]),
}

# A tool is only offered when the message sounds like its job.
_TOOL_TRIGGERS = {
    "add_reminder": re.compile(r"remind|reminder|alarm|wake me|alert me|don'?t let me forget|"
                               r"মনে\s*করি|রিমাইন্ড|অ্যালার্ম", re.I),
    "add_todo": re.compile(r"to-?\s?do|\btasks?\b|my list|task list|কাজের\s*তালিকা|টুডু|টু-ডু", re.I),
    "start_timer": re.compile(r"timer|countdown|count down|pomodoro|টাইমার", re.I),
    "log_study": re.compile(r"stud(?:y|ied|ying)|revis|\blog(?:ged)?\b|পড়|পড়ে|পড়া", re.I),
}
_DURATION = re.compile(r"\d+\s*(?:min|minute|hour|hr|h\b|মিনিট|ঘণ্টা|ঘন্টা)", re.I)


def pick_tools(text):
    """The tool specs that fit this message ([] = no tools, a normal chat answer)."""
    names = []
    for name, rx in _TOOL_TRIGGERS.items():
        if rx.search(text):
            if name == "log_study" and not _DURATION.search(text):
                continue                                    # "how do I study better?" is not a log
            names.append(name)
    return [TOOL_SPECS[n] for n in names]


def _estimate_tokens(text):
    """Rough token count. English is about 4 letters per token; Bangla and other scripts need many
    more tokens per letter, so they are counted much heavier (safe side)."""
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - ascii_chars
    return int(ascii_chars / 3.5 + other / 1.2) + 4


def _parse_args(raw):
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except ValueError:
            return {}
    try:
        return dict(raw)
    except Exception:
        return {}


_PY_CALL = re.compile(r"^\s*\[?\s*(\w+)\s*\((.*)\)\s*\]?\s*$", re.S)
_PY_ARG = re.compile(r"(\w+)\s*=\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|-?\d+(?:\.\d+)?)")


def tool_calls_from_text(text, allowed):
    """Small models sometimes write the tool call as text instead of using the tool API, e.g.
    {"name": "add_reminder", "parameters": {...}}  or  [start_timer(minutes=25)].
    Returns [(name, args)] or []."""
    t = text.strip()
    if t.startswith("<|python_tag|>"):
        t = t[len("<|python_tag|>"):].strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    found = []
    try:
        data = json.loads(t)
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            fn = it.get("function") if isinstance(it.get("function"), dict) else it
            name = fn.get("name")
            args = fn.get("parameters", fn.get("arguments", {}))
            if name in allowed:
                found.append((name, _parse_args(args)))
        return found
    except ValueError:
        pass
    m = _PY_CALL.match(t)
    if m and m.group(1) in allowed:
        args = {}
        for key, val in _PY_ARG.findall(m.group(2)):
            if val[:1] in "\"'":
                args[key] = val[1:-1]
            else:
                args[key] = float(val) if "." in val else int(val)
        return [(m.group(1), args)]
    return []


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
_CODE_LANGS = {"c", "cpp", "c++", "cs", "csharp", "python", "py", "java", "javascript", "js", "ts",
               "typescript", "bash", "sh", "shell", "json", "html", "css", "sql", "text", "txt", "rust",
               "go", "php", "ruby", "kotlin", "swift", "r", "xml", "yaml", "markdown", "md", "powershell"}


def _clean_prose(t):
    """Strip markdown from normal text (never used on code)."""
    t = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]+", "", t, flags=re.M)             # '# Heading' (needs a space: '#include' stays)
    t = re.sub(r"^[ \t]*[-*+][ \t]+", "• ", t, flags=re.M)           # bullets
    t = t.replace("**", "")
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"\1", t)
    t = re.sub(r"`([^`\n]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1", t)    # [text](url) -> text
    return t


def clean_reply(text):
    """Make a model answer look nice in a plain-text bubble (strip markdown).
    Code inside ``` fences is kept exactly as written (a '#include' or a '# comment' is code, not a
    heading). Safe to call on a half-finished (streamed) answer."""
    t = str(text).replace("\r\n", "\n")
    parts = t.split("```")
    out = []
    for i, seg in enumerate(parts):
        if i % 2 == 1:                                              # inside a code fence
            first, sep, rest = seg.partition("\n")
            if sep and first.strip().lower() in _CODE_LANGS | {""}:
                seg = rest                                          # drop the language tag line
            out.append("\n" + seg.strip("\n") + "\n")
        else:
            out.append(_clean_prose(seg))
    t = "".join(out)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _field(obj, *names):
    """Read a field from either a dict (old ollama versions) or an object (new ones)."""
    if obj is None:
        return None
    for name in names:
        try:
            value = obj[name]
            if value is not None:
                return value
        except Exception:
            pass
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _is_connection_error(e):
    low = str(e).lower()
    return (isinstance(e, ConnectionError)
            or "failed to connect" in low or "connection refused" in low
            or "refused" in low or "10061" in low or "connecterror" in type(e).__name__.lower()
            or "all connection attempts failed" in low)


def _no_tool_support(e):
    return "does not support tools" in str(e).lower()


def _find_ollama_exe():
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        files = os.environ.get("ProgramFiles", "")
        for cand in (os.path.join(local, "Programs", "Ollama", "ollama.exe"),
                     os.path.join(files, "Ollama", "ollama.exe")):
            if cand and os.path.exists(cand):
                return cand
    return None


# ----------------------------------------------------------------------
class LocalAIAssistant(QObject):
    response_chunk_received = Signal(str)
    response_finished = Signal(str)
    error_occurred = Signal(str)

    _chunk = Signal(int, str)
    _done = Signal(int, str)
    _failed = Signal(int, str)
    _tool_request = Signal(int, str, str, object)  # request id, tool name, arguments as JSON, reply box

    def __init__(self, model_name=DEFAULT_MODEL, host=None, history_file=None, tool_handler=None):
        super().__init__()
        self.model_name = model_name or DEFAULT_MODEL
        self.host = host
        self.history_file = history_file
        self.tool_handler = tool_handler   # fn(name, args) -> (ok, message); runs on the UI thread
        self.history = self._load_history()   # only user / assistant messages (the system prompt is rebuilt each time)
        self.busy = False
        self.partial = ""            # the answer so far (while streaming)
        self.last_raw = ""           # the last finished answer exactly as the model wrote it
        self._req = 0                # id of the current request
        self._cb = (None, None, None)
        self._server_tried = False
        self._no_tools = set()       # models that said they cannot use tools
        self._tool_event = None      # the event the worker is waiting on (cancel() sets it)
        self._chunk.connect(self._handle_chunk)
        self._done.connect(self._handle_done)
        self._failed.connect(self._handle_failed)
        self._tool_request.connect(self._run_tool_on_ui)

    def available(self):
        return ollama is not None

    def set_model(self, name):
        if name:
            self.model_name = name

    def reset(self):
        """Forget the conversation (and stop any answer in progress)."""
        self.cancel()
        self.history = []
        self._save_history()

    def _trim_history(self):
        """Drop the oldest messages until the chat fits HISTORY_TOKENS, but always keep the newest
        message, however long it is. The history always starts with a user message."""
        sizes = [_estimate_tokens(m["content"]) for m in self.history]
        total = sum(sizes)
        while len(self.history) > 1 and total > HISTORY_TOKENS:
            self.history.pop(0)
            total -= sizes.pop(0)
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    def _load_history(self):
        if not self.history_file or not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            msgs = [{"role": m["role"], "content": m["content"]} for m in data.get("messages", [])
                    if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                    and isinstance(m.get("content"), str) and m["content"].strip()]
        except Exception:
            return []
        self.history = msgs
        self._trim_history()
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()                   # a question that never got an answer
        return self.history

    def _save_history(self):
        if not self.history_file:
            return
        try:
            if not self.history:
                if os.path.exists(self.history_file):
                    os.remove(self.history_file)
                return
            tmp = self.history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"messages": self.history}, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.history_file)   # atomic: a crash never leaves half a file
        except OSError:
            pass

    def cancel(self):
        """Stop the answer in progress. Its callbacks will never be called."""
        if not self.busy:
            return
        self._req += 1                       # the worker sees a new id and stops
        self.busy = False
        self.partial = ""
        self._cb = (None, None, None)
        if self._tool_event is not None:
            self._tool_event.set()           # a worker waiting for a tool must not hang
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()               # that question never got an answer

    def list_models(self):
        """Names of the installed chat models ([] if Ollama is not reachable). Quick."""
        if ollama is None:
            return []
        try:
            return self._installed_models(self._client(timeout=3))
        except Exception:
            return []

    def ask_async(self, prompt, on_chunk=None, on_complete=None, on_error=None, context=None,
                  allow_tools=True):
        """Start the request in a background thread. Returns False if one is already running.
        on_chunk(text_so_far), on_complete(full_text), on_error(message) run on the UI thread.
        context = an earlier question the cat asked, so the model knows what the prompt answers.
        allow_tools=False: never offer tools (for example when asking about text from the screen)."""
        if self.busy:
            return False
        self._req += 1
        req = self._req
        self.busy = True
        self.partial = ""
        self._cb = (on_chunk, on_complete, on_error)

        raw = str(prompt)
        tools = pick_tools(raw) if (allow_tools and self.tool_handler is not None) else []
        content = raw
        if context:
            content = 'The cat had just asked: "%s"\nThe user answers: %s' % (context, content)
        # The time goes INTO the message (and is stored with it). The system prompt only has the
        # date, so it stays the same all day and Ollama can reuse its work on the old messages.
        content = "(%s) %s" % (datetime.now().strftime("%H:%M"), content)
        self.history.append({"role": "user", "content": content})
        self._trim_history()

        messages = [{"role": "system", "content": self._system_prompt(bool(tools))}] + list(self.history)
        threading.Thread(target=self._run, args=(req, messages, tools), daemon=True).start()
        return True

    def _system_prompt(self, with_tools=False):
        today = datetime.now().strftime("%A, %d %B %Y")
        text = ("You are a helpful, cute and concise desktop assistant cat who lives above the user's "
                "taskbar. Keep answers short and friendly (usually 1 to 4 sentences) because they are "
                "shown in a small chat bubble, BUT when the user asks for a long text (an essay, a "
                "story, a long explanation, a number of words), write all of it completely, never "
                "cut it short and never say it is too long. Use plain text only: no markdown, no asterisks, no "
                "headings, no tables. Reply in the language the user writes in. Many users are deaf and "
                "read English or Bangla as a second language, so use short, simple sentences and "
                "easy everyday words, and explain a difficult word the first time you use it. If you do "
                "not know something, say so honestly. Today is %s. Each user message starts with the "
                "local time it was sent, like (14:05); never repeat that time tag." % today)
        if with_tools:
            text += (" You can use tools to add reminders, to-dos, timers and study time. Call a tool ONLY "
                     "when the user clearly asks you to do one of these things. Copy the user's own words "
                     "for times and dates (for example 'friday at 8pm'); never invent a date. For any "
                     "other question, just answer normally.")
        return text

    def _client(self, timeout=REQUEST_TIMEOUT):
        kwargs = {"timeout": timeout}
        if self.host:
            kwargs["host"] = self.host
        return ollama.Client(**kwargs)

    @staticmethod
    def _installed_models(client):
        resp = client.list()
        models = _field(resp, "models") or []
        names = []
        for m in models:
            name = _field(m, "model", "name")
            if name and "embed" not in str(name).lower():
                names.append(str(name))
        return names

    def _resolve_model(self, client):
        """Use the configured model, or an installed one that matches, or the first installed one."""
        names = self._installed_models(client)
        if not names:
            raise RuntimeError("No AI model is installed yet. Run in a terminal:  ollama pull %s"
                               % self.model_name)
        want = self.model_name
        if want in names:
            return want
        for n in names:
            if n.split(":")[0] == want.split(":")[0] and (":" not in want or n == want):
                self.model_name = n          # e.g. "llama3.2" -> "llama3.2:latest"
                return n
        self.model_name = names[0]           # fall back to whatever is installed
        return names[0]

    def _start_server(self):
        """Try to start 'ollama serve' in the background. True if we launched something."""
        exe = _find_ollama_exe()
        if not exe:
            return False
        try:
            kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                      "stderr": subprocess.DEVNULL, "close_fds": True}
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x08000000 | 0x00000008   # no window, detached
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([exe, "serve"], **kwargs)
            return True
        except Exception:
            return False

    def _wait_for_server(self, req):
        deadline = time.time() + SERVER_WAIT_SECONDS
        while time.time() < deadline and req == self._req:
            try:
                self._client(timeout=2).list()
                return True
            except Exception:
                time.sleep(1.0)
        return False

    # ---------------------------------------------------------------- worker thread
    def _run(self, req, messages, tools):
        try:
            if ollama is None:
                raise RuntimeError("The 'ollama' Python package is not installed for this Python. "
                                   "Run:  pip install ollama   (%s)" % _IMPORT_ERROR)
            client = self._client()
            try:
                model = self._resolve_model(client)
            except Exception as e:
                if not (_is_connection_error(e) and not self._server_tried):
                    raise
                self._server_tried = True            # Ollama is not running: try to start it once
                if self._start_server() and self._wait_for_server(req):
                    model = self._resolve_model(client)
                else:
                    raise
            self._server_tried = False               # server is up: allow a restart attempt later
            if req != self._req:
                return
            if model in self._no_tools:
                tools = []
            try:
                full, calls = self._stream(client, model, messages, tools, req)
            except Exception as e:
                if not (tools and _no_tool_support(e)):
                    raise
                self._no_tools.add(model)            # this model cannot use tools: plain chat instead
                messages[0]["content"] = self._system_prompt(False)
                full, calls = self._stream(client, model, messages, [], req)
            if req != self._req:
                return
            allowed = {t["function"]["name"] for t in tools}
            if not calls and allowed:
                calls = tool_calls_from_text(full, allowed)
            if calls:
                full = self._do_tools(req, calls)
                if req != self._req:
                    return
            if not full.strip():
                raise RuntimeError("The model sent an empty answer. Try asking again.")
            self._done.emit(req, full)
        except Exception as e:
            if req == self._req:
                self._failed.emit(req, self._friendly_error(e))

    def _stream(self, client, model, messages, tools, req):
        """Read the answer. Returns (text, [(tool name, args)])."""
        kwargs = {"model": model, "messages": messages, "stream": True, "keep_alive": KEEP_ALIVE,
                  "options": {"num_predict": MAX_REPLY_TOKENS, "num_ctx": CONTEXT_TOKENS}}
        if tools:
            kwargs["tools"] = tools
        stream = client.chat(**kwargs)
        full, calls = "", []
        held = bool(tools)                   # with tools: wait to see if the text is a tool call
        for chunk in stream:
            if req != self._req:             # cancelled: stop reading, drop the connection
                close = getattr(stream, "close", None)
                if close:
                    try:
                        close()
                    except Exception:
                        pass
                return full, []
            msg = _field(chunk, "message")
            for call in _field(msg, "tool_calls") or []:
                fn = _field(call, "function")
                name = _field(fn, "name")
                if name:
                    calls.append((str(name), _parse_args(_field(fn, "arguments") or {})))
            text = _field(msg, "content") or ""
            if not text:
                continue
            full += text
            if held:
                start = full.lstrip()
                if not start:
                    continue
                if start[0] in "{[<`":       # looks like a tool call written as text: keep it back
                    continue
                held = False
                self._chunk.emit(req, full)  # it is a normal answer: show what we kept back
            else:
                self._chunk.emit(req, text)
        return full, calls

    def _do_tools(self, req, calls):
        """Run the tool calls in the app (UI thread) and build the cat's answer from the results."""
        lines = []
        seen = set()
        for name, args in calls[:4]:
            key = (name, json.dumps(args, sort_keys=True, default=str))
            if key in seen:                  # the model sometimes repeats the same call
                continue
            seen.add(key)
            ok, message = self._call_tool(req, name, args)
            if req != self._req:
                return ""
            lines.append(message)
        return "\n".join(lines) or "Sorry, I could not do that."

    def _call_tool(self, req, name, args):
        if self.tool_handler is None:
            return False, "I cannot do that here."
        # Each call gets its own reply box, so a late answer for an older (cancelled) request can
        # never be read as the answer to this one.
        box = {"event": threading.Event(), "result": None}
        self._tool_event = box["event"]
        self._tool_request.emit(req, name, json.dumps(args, default=str), box)
        if not box["event"].wait(TOOL_WAIT_SECONDS):
            return False, "Sorry, the app did not answer in time."
        result = box["result"]
        return result if result else (False, "Sorry, I could not do that.")

    # ---------------------------------------------------------------- UI thread
    @Slot(int, str, str, object)
    def _run_tool_on_ui(self, req, name, args_json, box):
        result = (False, "Sorry, I could not do that.")
        if req == self._req:
            try:
                args = json.loads(args_json)
                out = self.tool_handler(name, args if isinstance(args, dict) else {})
                if isinstance(out, tuple) and len(out) == 2:
                    result = (bool(out[0]), str(out[1]))
            except Exception as e:
                result = (False, "Sorry, that did not work: %s" % e)
        box["result"] = result
        box["event"].set()

    def _friendly_error(self, e):
        text = str(e)
        low = text.lower()
        if getattr(e, "status_code", None) == 404 or ("not found" in low and "model" in low):
            return "Model '%s' is not installed. Run in a terminal:  ollama pull %s" % (
                self.model_name, self.model_name)
        if _is_connection_error(e):
            return ("I can't reach Ollama. Start the Ollama app (or run 'ollama serve'), "
                    "then ask me again.")
        if "timed out" in low or "timeout" in low:
            return "The model took too long to answer. Try again, or pick a smaller model."
        return text or e.__class__.__name__

    @Slot(int, str)
    def _handle_chunk(self, req, text):
        if req != self._req or not self.busy:
            return
        self.partial += text
        self.response_chunk_received.emit(text)
        if self._cb[0]:
            self._cb[0](self.partial)

    @Slot(int, str)
    def _handle_done(self, req, full):
        if req != self._req or not self.busy:
            return
        reply = clean_reply(full) or full.strip()
        self.last_raw = full
        self.history.append({"role": "assistant", "content": reply})
        self._save_history()
        self.busy = False
        self.partial = ""
        cb = self._cb
        self._cb = (None, None, None)
        self.response_finished.emit(reply)
        if cb[1]:
            cb[1](reply)

    @Slot(int, str)
    def _handle_failed(self, req, err):
        if req != self._req or not self.busy:
            return
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()                       # drop the question that never got an answer
        self.busy = False
        self.partial = ""
        cb = self._cb
        self._cb = (None, None, None)
        self.error_occurred.emit(err)
        if cb[2]:
            cb[2](err)
