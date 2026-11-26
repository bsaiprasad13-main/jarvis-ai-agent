"""Where Jarvis keeps its files: a local folder, or a Zoho Catalyst Stratus bucket.

Both offer the same three calls, so the rest of the code doesn't care where it runs:
    read_text(key) -> str or None     write_text(key, text)     public_url(key)
"""
import os


class LocalStorage:
    def __init__(self, root):
        self.root = root

    def _path(self, key):
        return os.path.join(self.root, *key.split("/"))

    def read_text(self, key):
        p = self._path(key)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()

    def write_text(self, key, text):
        p = self._path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)

    def public_url(self, key):
        return self._path(key)


class StratusStorage:
    """A Catalyst Stratus bucket. Created in the console with the Public template (read-only for visitors)."""

    def __init__(self, app, bucket_name):
        self.bucket = app.stratus().bucket(bucket_name)

    def read_text(self, key):
        try:
            obj = self.bucket.get_object(key)
        except Exception:                      # missing object (first run) or not readable
            return None
        if hasattr(obj, "read"):
            obj = obj.read()
        elif not isinstance(obj, (bytes, str)):
            obj = b"".join(obj)                # iterator of chunks
        return obj.decode("utf-8") if isinstance(obj, bytes) else obj

    def write_text(self, key, text):
        ok = self.bucket.put_object(key, text.encode("utf-8"),
                                    {"overwrite": "true", "content_type": "application/json"})
        if not ok:
            raise IOError(f"Stratus upload failed for {key}")

    def public_url(self, key):
        return f"{self.bucket.bucket_domain}/{key}"
