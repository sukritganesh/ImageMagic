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
        self.running = []
        self.pending = []
        queue = SimpleNamespace(get_current_queue_volatile=lambda: (self.running, self.pending))
        files = {"diffusion_models": ["flux-2-klein-4b-fp8.safetensors"], "text_encoders": ["qwen_3_4b.safetensors"]}
        modules = {
            "folder_paths": SimpleNamespace(get_output_directory=lambda: temp.name, get_filename_list=files.__getitem__),
            "server": SimpleNamespace(PromptServer=SimpleNamespace(instance=SimpleNamespace(routes=routes, prompt_queue=queue))),
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

    def save_png(self, folder, digit="a", **lineage):
        name = digit * 32 + "_00001_.png"
        folder.mkdir(parents=True, exist_ok=True)
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("imagemagic", json.dumps({"model": "Klein 4B · FP8", "prompt": "A fox", "submitted": 0, **lineage}))
        Image.new("RGB", (1, 1)).save(folder / name, pnginfo=metadata)
        return name

    async def deletion_preview(self, session):
        response = await self.client.get(f"/studio/api/sessions/{session}/deletion")
        self.assertEqual(response.status, 200)
        return await response.json()

    async def delete_session(self, session, preview):
        return await self.client.post(f"/studio/api/sessions/{session}/delete", json=preview)

    async def test_delete_session_counts_versions_and_scopes_permanent_deletion(self):
        session = await self.create_session("Coast")
        keep = await self.create_session("Keep")
        folder = self.output / session
        original = self.save_png(folder)
        self.save_png(folder, "b", original=original, parent=original)
        self.save_png(folder, "c", original=original, parent=original)
        for neighbor in (self.output, self.output / keep):
            self.save_png(neighbor)
        before = await self.deletion_preview(session)
        self.assertEqual((before["images"], before["trashed"]), (3, 0))
        await self.client.post("/studio/api/delete", json={"session": session, "file": original, "scope": "version"})
        self.assertEqual((await self.delete_session(session, {})).status, 400)
        self.assertEqual((await self.delete_session(session, before)).status, 409)
        current = await self.deletion_preview(session)
        self.assertEqual((current["images"], current["trashed"]), (2, 1))
        self.assertEqual(await (await self.delete_session(session, current)).json(), {"deleted": 3})
        self.assertFalse(folder.exists())
        self.assertEqual((await self.client.get(f"/studio/session/{session}")).status, 404)
        self.assertTrue((self.output / keep / original).is_file())
        self.assertTrue((self.output / original).is_file())

    async def test_delete_previous_images_preserves_named_sessions_and_unrelated_files(self):
        keep = await self.create_session("Named session")
        saved = self.save_png(self.output / keep)
        self.save_png(self.output)
        await self.client.post("/studio/api/delete", json={"file": saved, "scope": "version"})
        self.save_png(self.output, "b")
        unrelated = self.output / "reference.png"
        Image.new("RGB", (1, 1)).save(unrelated)
        preview = await self.deletion_preview("previous")
        self.assertEqual((preview["images"], preview["trashed"]), (1, 1))
        self.assertEqual((await self.delete_session("previous", preview)).status, 200)
        home = await (await self.client.get("/studio")).text()
        self.assertNotIn("Previous images", home)
        self.assertIn("Named session", home)
        self.assertTrue((self.output / keep / saved).is_file())
        self.assertTrue(unrelated.is_file())
        self.assertFalse((self.output / ".trash").exists())

    async def test_delete_empty_session_checks_pending_and_running_jobs(self):
        session = await self.create_session("Empty")
        other = await self.create_session("Other")
        preview = await self.deletion_preview(session)
        self.assertEqual((preview["images"], preview["trashed"]), (0, 0))
        await self.client.post("/studio/api/generate", json={"session": session, "prompt": "A hill"})
        for queue in (self.pending, self.running):
            queue.append((0, "job", self.queued["prompt"]))
            self.assertEqual((await self.delete_session(session, preview)).status, 409)
            self.assertTrue((self.output / session / "name.txt").is_file())
            queue.clear()
        await self.client.post("/studio/api/generate", json={"session": other, "prompt": "A lake"})
        self.pending.append((0, "other", self.queued["prompt"]))
        self.assertEqual((await self.delete_session(session, preview)).status, 200)
        self.assertFalse((self.output / session).exists())

    async def test_can_review_remaining_images_after_a_locked_file(self):
        session = await self.create_session("Locked file")
        folder = self.output / session
        self.save_png(folder)
        locked = self.save_png(folder, "b")
        unlink = Path.unlink

        def fail_if_locked(path, **kwargs):
            if path.name == locked:
                raise PermissionError("locked")
            return unlink(path, **kwargs)

        with patch.object(Path, "unlink", fail_if_locked):
            preview = await self.deletion_preview(session)
            self.assertEqual((await self.delete_session(session, preview)).status, 409)
        remaining = await self.deletion_preview(session)
        self.assertGreaterEqual(remaining["images"], 1)
        self.assertEqual((await self.delete_session(session, remaining)).status, 200)
        self.assertFalse(folder.exists())

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

    async def test_delete_ancestors_keeps_later_edits_editable_and_restorable(self):
        original = self.save_png(self.output)
        middle = self.save_png(self.output, "b", original=original, parent=original)
        latest = self.save_png(self.output, "c", original=original, parent=middle)
        other = self.save_png(self.output, "d")
        expected = [original, middle, latest]
        for name in (middle, original):
            response = await self.client.post("/studio/api/delete", json={"scope": "version", "file": name})
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["deleted"], [name])
            expected.remove(name)
            items = await (await self.client.get("/studio/api/gallery")).json()
            self.assertCountEqual([i["file"] for i in items], [*expected, other])
        edit = await self.client.post("/studio/api/edit", json={"source": latest, "prompt": "Add a scarf"})
        self.assertEqual(edit.status, 200)
        self.assertEqual(self.queued["extra_data"]["extra_pnginfo"]["imagemagic"]["original"], original)
        self.assertEqual(self.queued["prompt"]["14"]["inputs"]["image"], f"ImageMagic/{latest} [output]")
        deletion = await self.client.post("/studio/api/delete", json={"scope": "card", "file": latest, "versions": expected})
        self.assertEqual(deletion.status, 200)
        self.assertTrue((self.output / other).exists())
        for name in (original, middle, latest):
            (trashed,) = (self.output / ".trash").glob("*/" + name)
            trashed.rename(self.output / name)
        restored = await (await self.client.get("/studio/api/gallery")).json()
        self.assertCountEqual([i["file"] for i in restored], [original, middle, latest, other])

    async def test_delete_card_is_session_scoped_and_checks_confirmed_versions_and_queue(self):
        session = await self.create_session("Coast")
        folder = self.output / session
        original = self.save_png(folder)
        edit = self.save_png(folder, "b", original=original, parent=original)
        self.save_png(self.output)
        payload = {"scope": "card", "session": session, "file": original, "versions": [original]}
        self.assertEqual((await self.client.post("/studio/api/delete", json=payload)).status, 409)
        payload["versions"].append(edit)
        self.pending.append((0, "job", {"14": {"class_type": "LoadImage", "inputs": {"image": f"ImageMagic/{session}/{edit} [output]"}}}))
        self.assertEqual((await self.client.post("/studio/api/delete", json=payload)).status, 409)
        self.assertTrue((folder / original).exists())
        self.assertTrue((folder / edit).exists())
        self.pending.clear()
        result = await self.client.post("/studio/api/delete", json=payload)
        self.assertCountEqual((await result.json())["deleted"], [original, edit])
        self.assertTrue((self.output / original).exists())
        self.assertEqual(await (await self.client.get(f"/studio/api/gallery?session={session}")).json(), [])
        self.assertEqual((await self.client.post("/studio/api/delete", json=payload)).status, 404)

    async def test_failed_batch_move_restores_already_moved_files(self):
        original = self.save_png(self.output)
        edit = self.save_png(self.output, "b", original=original, parent=original)
        rename = Path.rename
        moved = []

        def fail_second_move(path, dest):
            if path.parent == self.output:
                if moved:
                    raise PermissionError("file is busy")
                moved.append(path)
            return rename(path, dest)

        with patch.object(Path, "rename", fail_second_move):
            response = await self.client.post("/studio/api/delete", json={
                "scope": "card", "file": edit, "versions": [original, edit],
            })
        self.assertEqual(response.status, 409)
        self.assertTrue(moved)
        self.assertCountEqual([p.name for p in self.output.glob("*.png")], [original, edit])

    async def test_empty_trash_only_purges_confirmed_files_in_the_selected_session(self):
        session = await self.create_session("Keep")
        saved = self.save_png(self.output / session)
        active = self.save_png(self.output / session, "d")

        async def discard(session_id, name):
            response = await self.client.post("/studio/api/delete", json={"session": session_id, "scope": "version", "file": name})
            self.assertEqual(response.status, 200)

        await discard(session, saved)
        await discard("previous", self.save_png(self.output))
        self.assertIn("Previous images", await (await self.client.get("/studio")).text())
        first = await (await self.client.get("/studio/api/trash?session=previous")).json()
        self.assertEqual(first["count"], 1)
        await discard("previous", self.save_png(self.output, "b"))
        payload = {"session": "previous", "revision": first["revision"]}
        self.assertEqual((await self.client.post("/studio/api/trash/empty", json=payload)).status, 409)
        latest = await (await self.client.get("/studio/api/trash?session=previous")).json()
        self.assertEqual(latest["count"], 2)
        payload["revision"] = latest["revision"]
        result = await self.client.post("/studio/api/trash/empty", json=payload)
        self.assertEqual(await result.json(), {"deleted": 2})
        self.assertFalse((self.output / ".trash").exists())
        self.assertNotIn("Previous images", await (await self.client.get("/studio")).text())
        remaining = await (await self.client.get("/studio/api/trash?session=" + session)).json()
        self.assertEqual(remaining["count"], 1)
        response = await self.client.post("/studio/api/trash/empty", json={"session": session, "revision": remaining["revision"]})
        self.assertEqual(await response.json(), {"deleted": 1})
        self.assertTrue((self.output / session / active).is_file())

    async def test_empty_trash_can_retry_after_a_locked_file(self):
        for digit in "ab":
            name = self.save_png(self.output, digit)
            await self.client.post("/studio/api/delete", json={"file": name, "scope": "version"})
        unlink = Path.unlink

        def fail_on_second(path, **kwargs):
            if path.name.startswith("b"):
                raise PermissionError("locked")
            return unlink(path, **kwargs)

        async def purge():
            info = await (await self.client.get("/studio/api/trash")).json()
            return await self.client.post("/studio/api/trash/empty", json={"session": "previous", "revision": info["revision"]})

        with patch.object(Path, "unlink", fail_on_second):
            self.assertEqual((await purge()).status, 409)
        self.assertEqual((await purge()).status, 200)
        self.assertFalse((self.output / ".trash").exists())
        self.assertEqual((await (await self.client.get("/studio/api/trash")).json())["count"], 0)
