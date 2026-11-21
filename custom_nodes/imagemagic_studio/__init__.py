"""Local prompt gallery for the installed FLUX.2 Klein checkpoints."""
import asyncio
import hashlib
import json
import re
import secrets
import time
import uuid
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import NamedTuple

from aiohttp import ClientSession, web
from PIL import Image
import folder_paths
from server import PromptServer

NODE_CLASS_MAPPINGS = {}
ROOT = Path(__file__).parent
OUTPUT = Path(folder_paths.get_output_directory()) / "ImageMagic"


class Model(NamedTuple):
    label: str
    checkpoint: str
    encoder: str = "qwen_3_4b.safetensors"


MODELS = {
    "fp8": Model("Klein 4B · FP8", "flux-2-klein-4b-fp8.safetensors"),
    "9b-fp8": Model("Klein 9B · FP8", "flux-2-klein-9b-fp8.safetensors", "qwen_3_8b_fp8mixed.safetensors"),
    "nvfp4": Model("Klein 4B · Compact", "flux-2-klein-4b-nvfp4.safetensors"),
    "base": Model("Klein 4B Base · FP8", "flux-2-klein-base-4b-fp8.safetensors"),
}


def installed_models():
    checkpoints = folder_paths.get_filename_list("diffusion_models")
    encoders = folder_paths.get_filename_list("text_encoders")
    return {key: model.label for key, model in MODELS.items()
            if model.checkpoint in checkpoints and model.encoder in encoders}


def workflow(prompt, model, seed, run_id, source=None):
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}

    graph = {
        "1": node("UNETLoader", unet_name=MODELS[model].checkpoint, weight_dtype="default"),
        "2": node("CLIPLoader", clip_name=MODELS[model].encoder, type="flux2",
                  device="cpu" if model == "nvfp4" else "default"),
        "3": node("VAELoader", vae_name="flux2-vae.safetensors"),
        "4": node("CLIPTextEncode", clip=["2", 0], text=prompt),
        "5": node("EmptyFlux2LatentImage", width=1024, height=1024, batch_size=1),
        "6": node("RandomNoise", noise_seed=seed),
        "7": node("KSamplerSelect", sampler_name="euler"),
        "8": node("Flux2Scheduler", steps=50 if model == "base" else 4, width=1024, height=1024),
        "9": node("BasicGuider", model=["1", 0], conditioning=["4", 0]),
        "10": node("SamplerCustomAdvanced", noise=["6", 0], guider=["9", 0], sampler=["7", 0],
                   sigmas=["8", 0], latent_image=["5", 0]),
        "11": node("VAEDecode", samples=["10", 0], vae=["3", 0]),
        "12": node("SaveImage", images=["11", 0], filename_prefix=f"ImageMagic/{run_id}"),
    }
    if model == "base":
        graph["13"] = node("CLIPTextEncode", clip=["2", 0], text="")
        graph["9"] = node("CFGGuider", model=["1", 0], positive=["4", 0], negative=["13", 0], cfg=4.0)
    if source:
        graph["14"] = node("LoadImage", image=f"ImageMagic/{source} [output]")
        graph["15"] = node("VAEEncode", pixels=["14", 0], vae=["3", 0])
        graph["16"] = node("ReferenceLatent", conditioning=["4", 0], latent=["15", 0])
        if model == "base":
            graph["17"] = node("ReferenceLatent", conditioning=["13", 0], latent=["15", 0])
            graph["9"]["inputs"].update(positive=["16", 0], negative=["17", 0])
        else:
            graph["9"]["inputs"]["conditioning"] = ["16", 0]
    return graph


routes = PromptServer.instance.routes
# Serialize deletion with handing an edit's source to ComfyUI's queue.
edit_queue_lock = asyncio.Lock()


def session_directory(session_id):
    if session_id == "previous":
        return OUTPUT
    if isinstance(session_id, str) and re.fullmatch(r"[0-9a-f]{32}", session_id):
        folder = OUTPUT / session_id
        if (folder / "name.txt").is_file():
            return folder
    raise web.HTTPNotFound(text="Session not found.")


@routes.get("/studio")
async def studio(request):
    sessions = []
    for marker in OUTPUT.glob("*/name.txt"):
        session_id = marker.parent.name
        if re.fullmatch(r"[0-9a-f]{32}", session_id):
            sessions.append((marker.stat().st_mtime, session_id, marker.read_text(encoding="utf-8")))
    sessions.sort(reverse=True)
    if any(OUTPUT.glob("*.png")) or (OUTPUT / ".trash").is_dir():
        sessions.append((0, "previous", "Previous images"))
    rows = "".join(
        f'<li><a href="/studio/session/{session_id}"><span>{escape(name)}</span>'
        f'<span aria-hidden="true">→</span></a></li>' for _, session_id, name in sessions
    )
    contents = f'<ul class="session-list">{rows}</ul>' if rows else '<p class="empty-list">No sessions yet.</p>'
    page = (ROOT / "sessions.html").read_text(encoding="utf-8").replace("{{sessions}}", contents)
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


@routes.post("/studio/sessions")
async def create_session(request):
    form = await request.post()
    name = form.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise web.HTTPBadRequest(text="Enter a session name between 1 and 80 characters.")
    folder = OUTPUT / uuid.uuid4().hex
    folder.mkdir(parents=True)
    pending = folder / "name.tmp"
    pending.write_text(name.strip(), encoding="utf-8")
    pending.replace(folder / "name.txt")
    raise web.HTTPSeeOther(location=f"/studio/session/{folder.name}")


@routes.get("/studio/session/{session_id}")
async def open_session(request):
    folder = session_directory(request.match_info["session_id"])
    name = "Previous images" if folder == OUTPUT else (folder / "name.txt").read_text(encoding="utf-8")
    page = (ROOT / "studio.html").read_text(encoding="utf-8").replace("{{session_name}}", escape(name))
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


@routes.get("/studio/style.css")
async def stylesheet(request):
    return web.FileResponse(ROOT / "style.css")


@routes.get("/studio/api/models")
async def models(request):
    return web.json_response(installed_models())


@routes.post("/studio/api/generate")
async def generate(request):
    body = await request.json()
    folder = session_directory(body.get("session", "previous"))
    return await submit(request, body.get("prompt"), body.get("model", "fp8"), folder=folder)


@routes.post("/studio/api/edit")
async def edit(request):
    body = await request.json()
    async with edit_queue_lock:
        return await queue_edit(request, body)


async def queue_edit(request, body):
    source = body.get("source")
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{32}_\d+_\.png", source):
        raise web.HTTPBadRequest(text="Choose an image from the studio gallery.")
    folder = session_directory(body.get("session", "previous"))
    path = folder / source
    try:
        parent = image_info(path, path.stat().st_mtime)
    except (OSError, ValueError, KeyError):
        raise web.HTTPNotFound(text="The selected image is no longer available.")
    model = parent.get("model_id")
    if model is None:  # Older studio PNGs store only the display name.
        model = next((key for key, spec in MODELS.items() if spec.label == parent["model"]), None)
    return await submit(request, body.get("prompt"), model, parent)


async def submit(request, prompt, model, parent=None, *, folder=OUTPUT):
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not prompt or len(prompt) > 8000 or not isinstance(model, str) or model not in installed_models():
        raise web.HTTPBadRequest(text="Enter a prompt and choose an installed model.")
    run_id = uuid.uuid4().hex
    seed = secrets.randbits(52)
    info = {"prompt": prompt, "model": MODELS[model].label, "model_id": model,
            "seed": seed, "submitted": time.time()}
    source = None
    if parent:
        source = parent["file"]
        info.update(parent=source, original=parent.get("original", source))
        folder = OUTPUT.parent / parent["subfolder"]
    relative = folder.relative_to(OUTPUT)
    output_prefix = (relative / run_id).as_posix()
    reference = (relative / source).as_posix() if source else None
    payload = {"prompt": workflow(prompt, model, seed, output_prefix, reference),
               "extra_data": {"extra_pnginfo": {"imagemagic": info}}}
    port = request.transport.get_extra_info("sockname")[1]
    async with ClientSession() as session:
        async with session.post(f"http://127.0.0.1:{port}/prompt", json=payload) as result:
            return web.Response(body=await result.read(), status=result.status, content_type="application/json")


@lru_cache(maxsize=2048)
def image_info(path, modified):
    with Image.open(path) as image:
        info = json.loads(image.info["imagemagic"])
    return {**info, "file": path.name, "subfolder": path.parent.relative_to(OUTPUT.parent).as_posix(),
            "seconds": round(max(0, modified - info["submitted"]), 1)}


def gallery_images(folder):
    items = []
    for path in folder.glob("*.png"):
        try:
            items.append(image_info(path, path.stat().st_mtime))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(items, key=lambda item: item["submitted"], reverse=True)


@routes.get("/studio/api/gallery")
async def gallery(request):
    folder = session_directory(request.query.get("session", "previous"))
    return web.json_response(gallery_images(folder), headers={"Cache-Control": "no-store"})


def trash_directory(folder):
    trash = folder / ".trash"
    expected = OUTPUT.resolve() / folder.relative_to(OUTPUT) / ".trash"
    if trash.resolve() != expected:
        raise web.HTTPBadRequest(text="Invalid gallery trash location.")
    return expected


def move_to_trash(folder, filenames):
    trash = trash_directory(folder)
    batch = trash / uuid.uuid4().hex
    batch.mkdir(parents=True)
    moved = []
    try:
        for name in filenames:
            (folder / name).rename(batch / name)
            moved.append(name)
    except OSError:
        for name in reversed(moved):
            (batch / name).rename(folder / name)
        batch.rmdir()
        raise


@routes.post("/studio/api/delete")
async def delete_images(request):
    body = await request.json()
    if not isinstance(body, dict) or body.get("scope") not in ("version", "card"):
        raise web.HTTPBadRequest(text="Choose a version or an entire card.")
    folder = session_directory(body.get("session", "previous"))
    async with edit_queue_lock:
        running, queued = PromptServer.instance.prompt_queue.get_current_queue_volatile()
        items = gallery_images(folder)
        selected = next((item for item in items if item["file"] == body.get("file")), None)
        if selected is None:
            raise web.HTTPNotFound(text="That image is no longer in this session.")
        filenames = [selected["file"]]
        if body["scope"] == "card":
            root = selected.get("original") or selected["file"]
            filenames = [item["file"] for item in items if (item.get("original") or item["file"]) == root]
            expected = body.get("versions")
            if not isinstance(expected, list) or not all(isinstance(name, str) for name in expected):
                raise web.HTTPBadRequest(text="Confirm the versions to delete.")
            if sorted(expected) != sorted(filenames):
                raise web.HTTPConflict(text="This card has changed. Review its versions and try again.")
        references = {f"{selected['subfolder']}/{name} [output]" for name in filenames}
        for job in (*running, *queued):
            for node in job[2].values():
                source = node.get("inputs", {}).get("image")
                if node.get("class_type") == "LoadImage" and isinstance(source, str) and source in references:
                    raise web.HTTPConflict(text="An edit is using this image. Try again when it finishes.")
        try:
            move_to_trash(folder, filenames)
        except OSError as error:
            raise web.HTTPConflict(text="Could not move the images to trash. Check the files and try again.") from error
    return web.json_response({"deleted": filenames})


def trash_batches(trash):
    for batch in trash.glob("*"):
        if re.fullmatch(r"[0-9a-f]{32}", batch.name) and batch.resolve() == batch and batch.is_dir():
            yield batch


def trash_snapshot(trash):
    images = []
    for batch in trash_batches(trash):
        images.extend(path for path in batch.glob("*.png") if path.resolve() == path and path.is_file())
    names = sorted(path.relative_to(trash).as_posix() for path in images)
    revision = hashlib.sha256(json.dumps(names).encode()).hexdigest()
    return images, revision


@routes.get("/studio/api/trash")
async def trash_info(request):
    folder = session_directory(request.query.get("session", "previous"))
    images, revision = trash_snapshot(trash_directory(folder))
    return web.json_response({"count": len(images), "revision": revision}, headers={"Cache-Control": "no-store"})


@routes.post("/studio/api/trash/empty")
async def empty_trash(request):
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("revision"), str) or "session" not in body:
        raise web.HTTPBadRequest(text="Choose a session and confirm what is in its trash.")
    trash = trash_directory(session_directory(body["session"]))
    # Scanning and unlinking are synchronous, so studio requests cannot interleave here.
    images, revision = trash_snapshot(trash)
    if body["revision"] != revision:
        raise web.HTTPConflict(text="The trash has changed. Choose Empty trash again to review it.")
    try:
        for image in images:
            if image.resolve() != image:
                raise web.HTTPConflict(text="The trash has changed. Review it again.")
            image.unlink(missing_ok=True)
        for directory in [*trash_batches(trash), trash]:
            if directory.resolve() == directory and directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    except OSError as error:
        raise web.HTTPConflict(text="Could not finish emptying the trash. Check the remaining files and try again.") from error
    return web.json_response({"deleted": len(images)})
