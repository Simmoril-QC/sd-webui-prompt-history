import time
import json

class History(json.JSONEncoder):
    def __init__(self, id, name = "empty", model = "empty", prompt = "", info_text = "", params = ""):
        self.id = id
        self.name = name
        self.model = model
        # the prompt is the main stored content (first line of the generation info)
        raw = prompt or info_text or ""
        self.prompt = raw.splitlines(True)[0].rstrip("\n").strip()
        # optional: full generation info (prompt + parameters), kept when the
        # "Also save generation parameters" option is enabled
        self.params = params or ""
        self.created_at = time.time()

    def to_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "prompt": self.prompt,
            "params": self.params,
            "created_at": self.created_at,
        }
