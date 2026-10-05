import time
import json

class History(json.JSONEncoder):
    def __init__(self, id, name = "empty", model = "empty", prompt = "", info_text = ""):
        self.id = id
        self.name = name
        self.model = model
        # the prompt is the only stored content (generation parameters are dropped);
        # always normalize to the first line (covers legacy "prompt"/"info_text" values)
        raw = prompt or info_text or ""
        self.prompt = raw.splitlines(True)[0].rstrip("\n").strip()
        self.created_at = time.time()

    def to_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "prompt": self.prompt,
            "created_at": self.created_at,
        }
