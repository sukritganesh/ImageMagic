import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, PngImagePlugin


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / "ImageMagic"
        routes = web.RouteTableDef()
        files = {"diffusion_models": ["flux-2-klein-4b-fp8.safetensors"], "text_encoders": ["qwen_3_4b.safetensors"]}
        modules = {
            "folder_paths": SimpleNamespace(get_output_directory=lambda: temp.name, get_filename_list=files.__getitem__),
            "server": SimpleNamespace(PromptServer=SimpleNamespace(instance=SimpleNamespace(routes=routes))),
        }
        with patch.dict(sys.modules, modules):
            runpy.run_path(str(Path(__file__).resolve().parents[1] / "custom_nodes/imagemagic_studio/__init__.py"))

        async def record_prompt(request):
            self.queued = await request.json()
            return web.json_response({"prompt_id": "test"})

        app = web.Application()
        app.add_routes(routes)
        app.router.add_post("/prompt", record_prompt)
        self.client = TestClient(TestServer(app, host="127.0.0.1"))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def create_session(self, name):
        response = await self.client.post("/studio/sessions", data={"name": name}, allow_redirects=False)
        self.assertEqual(response.status, 303)
        return response.headers["Location"].rsplit("/", 1)[1]

    def save_png(self, folder):
        name = "a" * 32 + "_00001_.png"
        folder.mkdir(parents=True, exist_ok=True)
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("imagemagic", json.dumps({"model": "Klein 4B · FP8", "prompt": "A fox", "submitted": 0}))
        Image.new("RGB", (1, 1)).save(folder / name, pnginfo=metadata)
        return name

    async def test_home_lists_named_sessions_and_preserves_the_previous_gallery(self):
        self.assertIn("No sessions yet.", await (await self.client.get("/studio")).text())
        name = self.save_png(self.output)
        session = await self.create_session(" Sky & sea ")
        home = await (await self.client.get("/studio")).text()
        self.assertIn("Previous images", home)
        self.assertIn(f'/studio/session/{session}', home)
        page = await (await self.client.get(f"/studio/session/{session}")).text()
        self.assertIn("<h1>Sky &amp; sea</h1>", page)
        for query in ("", "?session=previous"):
            items = await (await self.client.get("/studio/api/gallery" + query)).json()
            self.assertEqual([(item["file"], item["subfolder"]) for item in items], [(name, "ImageMagic")])
        self.assertEqual(await (await self.client.get(f"/studio/api/gallery?session={session}")).json(), [])
        self.assertEqual((await self.client.post("/studio/sessions", data={"name": "  "})).status, 400)
        self.assertEqual((await self.client.get("/studio/session/missing")).status, 404)

    async def test_generation_and_edits_stay_in_the_chosen_session(self):
        first = await self.create_session("Woodland")
        second = await self.create_session("Night sky")
        response = await self.client.post("/studio/api/generate", json={"session": first, "prompt": "A fox"})
        self.assertEqual(response.status, 200)
        self.assertTrue(self.queued["prompt"]["12"]["inputs"]["filename_prefix"].startswith(f"ImageMagic/{first}/"))
        name = self.save_png(self.output / first)
        payload = {"source": name, "prompt": "Add a scarf", "session": second}
        self.assertEqual((await self.client.post("/studio/api/edit", json=payload)).status, 404)
        payload["session"] = first
        self.assertEqual((await self.client.post("/studio/api/edit", json=payload)).status, 200)
        self.assertEqual(self.queued["prompt"]["14"]["inputs"]["image"], f"ImageMagic/{first}/{name} [output]")
        self.assertEqual(self.queued["extra_data"]["extra_pnginfo"]["imagemagic"]["original"], name)
        self.assertEqual(await (await self.client.get(f"/studio/api/gallery?session={second}")).json(), [])
        items = await (await self.client.get(f"/studio/api/gallery?session={first}")).json()
        self.assertEqual(items[0]["subfolder"], f"ImageMagic/{first}")
