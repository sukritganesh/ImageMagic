import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web
from PIL import Image, PngImagePlugin
from studio_fixture import load_studio


class StudioModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        available = {
            "diffusion_models": ["flux-2-klein-4b-fp8.safetensors", "flux-2-klein-9b-fp8.safetensors"],
            "text_encoders": ["qwen_3_4b.safetensors"],
        }
        self.encoders = available["text_encoders"]
        modules = {
            "folder_paths": SimpleNamespace(get_output_directory=lambda: temp.name, get_filename_list=available.__getitem__),
            "server": SimpleNamespace(PromptServer=SimpleNamespace(instance=SimpleNamespace(routes=web.RouteTableDef()))),
        }
        self.studio = load_studio(modules)

    def test_9b_requires_its_encoder_and_keeps_4b_first(self):
        installed = self.studio["installed_models"]
        self.assertEqual(list(installed()), ["fp8"])
        self.encoders.append("qwen_3_8b_fp8mixed.safetensors")
        self.assertEqual(list(installed()), ["fp8", "9b-fp8"])

    def test_generate_and_edit_use_the_9b_checkpoint_and_encoder(self):
        for source in (None, "original.png"):
            with self.subTest(source=source):
                graph = self.studio["workflow"]("a gate", "9b-fp8", 1, "test", source)
                self.assertEqual(graph["1"]["inputs"]["unet_name"], "flux-2-klein-9b-fp8.safetensors")
                self.assertEqual(graph["2"]["inputs"]["clip_name"], "qwen_3_8b_fp8mixed.safetensors")
                self.assertEqual(graph["8"]["inputs"]["steps"], 4)
                if source:
                    self.assertEqual(graph["9"]["inputs"]["conditioning"], ["16", 0])
                    self.assertEqual(graph["14"]["inputs"]["image"], "ImageMagic/original.png [output]")

    async def test_edit_recovers_model_from_old_and_new_pngs(self):
        output = self.studio["OUTPUT"]
        output.mkdir()
        edit = self.studio["edit"]
        for index, (model_fields, expected) in enumerate([
            ({"model": "Klein 4B · FP8"}, "fp8"),
            ({"model": "Klein 9B · FP8", "model_id": "9b-fp8"}, "9b-fp8"),
        ]):
            with self.subTest(expected=expected):
                filename = f"{index:032x}_00001_.png"
                meta = PngImagePlugin.PngInfo()
                meta.add_text("imagemagic", json.dumps({**model_fields, "submitted": 0}))
                Image.new("RGB", (1, 1)).save(output / filename, pnginfo=meta)
                request = SimpleNamespace(json=AsyncMock(return_value={"source": filename, "prompt": "add a gate"}))
                submit = AsyncMock()
                with patch.dict(edit.__globals__, submit=submit):
                    await edit(request)
                self.assertEqual(submit.await_args.args[2], expected)
                self.assertEqual(submit.await_args.args[3]["file"], filename)
