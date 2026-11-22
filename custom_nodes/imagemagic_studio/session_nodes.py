"""ComfyUI image I/O for registered external sessions."""
import hashlib
import json
import tempfile
from pathlib import Path

import folder_paths
from PIL import Image

from .storage import Catalog, IMAGE_NAME, SESSION_ID


def external_folder(session_id):
    catalog = Catalog(Path(folder_paths.get_output_directory()) / "ImageMagic")
    session = catalog.get(session_id)
    if not session.custom:
        raise ValueError("Choose a session with a custom save location.")
    return session.require_folder()


class SaveSessionImage:
    CATEGORY = "ImageMagic"
    FUNCTION = "save"
    RETURN_TYPES = ()
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "session_id": ("STRING",), "run_id": ("STRING",)},
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    def save(self, images, session_id, run_id, prompt=None, extra_pnginfo=None):
        from nodes import SaveImage

        if not SESSION_ID.fullmatch(run_id):
            raise ValueError("Invalid image identifier.")
        folder = external_folder(session_id)
        # Keep partial PNGs out of the gallery if encoding or writing fails.
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            writer = SaveImage()
            writer.output_dir = tmp
            result = writer.save_images(images, run_id, prompt, extra_pnginfo)
            for entry in result["ui"]["images"]:
                filename = entry["filename"]
                (Path(tmp) / filename).rename(folder / filename)
        return ()


class LoadSessionImage:
    CATEGORY = "ImageMagic"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"session_id": ("STRING",), "filename": ("STRING",)}}

    @staticmethod
    def image_path(session_id, filename):
        if not IMAGE_NAME.fullmatch(filename):
            raise ValueError("Invalid session image filename.")
        path = external_folder(session_id) / filename
        if path.resolve(strict=True) != path:
            raise ValueError("Invalid session image location.")
        return path

    @classmethod
    def IS_CHANGED(cls, session_id, filename):
        with cls.image_path(session_id, filename).open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()

    def load(self, session_id, filename):
        import numpy as np
        import torch

        with Image.open(self.image_path(session_id, filename)) as png:
            if json.loads(png.info["imagemagic"]).get("session_id") != session_id:
                raise ValueError("This image does not belong to the session.")
            pixels = np.asarray(png.convert("RGB"), dtype=np.float32) / 255
        return (torch.from_numpy(pixels).unsqueeze(0),)


NODE_CLASS_MAPPINGS = {"ImageMagicSaveSessionImage": SaveSessionImage, "ImageMagicLoadSessionImage": LoadSessionImage}
