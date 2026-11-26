"""Local image generation and editing studio for ComfyUI."""
import asyncio
import hashlib
import json
import re
import secrets
import subprocess
import time
import uuid
from functools import lru_cache
from html import escape
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from aiohttp import ClientSession, web
from PIL import Image
import folder_paths
from server import PromptServer
from .session_nodes import NODE_CLASS_MAPPINGS
from .storage import Catalog, FolderUnavailable, IMAGE_NAME

ROOT = Path(__file__).parent
OUTPUT = (Path(folder_paths.get_output_directory()) / "ImageMagic").resolve()
catalog = Catalog(OUTPUT)


class Model(NamedTuple):
    label: str
    checkpoint: str
    encoder: str = "qwen_3_4b.safetensors"
    vae: str = "flux2-vae.safetensors"
    clip_type: str = "flux2"
    edit_with: str | None = None


MODELS = {
    "fp8": Model("Klein 4B · FP8", "flux-2-klein-4b-fp8.safetensors"),
    "9b-fp8": Model("Klein 9B · FP8", "flux-2-klein-9b-fp8.safetensors", "qwen_3_8b_fp8mixed.safetensors"),
    "nvfp4": Model("Klein 4B · Compact", "flux-2-klein-4b-nvfp4.safetensors"),
    "base": Model("Klein 4B Base · FP8", "flux-2-klein-base-4b-fp8.safetensors"),
    "z-image-turbo": Model("Z-Image-Turbo · BF16", "z_image_turbo_bf16.safetensors",
                          vae="ae.safetensors", clip_type="lumina2", edit_with="fp8"),
}


def installed_models():
    checkpoints = folder_paths.get_filename_list("diffusion_models")
    encoders = folder_paths.get_filename_list("text_encoders")
    vaes = folder_paths.get_filename_list("vae")
    return {key: model.label for key, model in MODELS.items()
            if model.checkpoint in checkpoints and model.encoder in encoders and model.vae in vaes}


def workflow(prompt, model, seed, run_id, source=None, *, external_session=None):
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}

    spec = MODELS[model]
    graph = {
        "1": node("UNETLoader", unet_name=spec.checkpoint, weight_dtype="default"),
        "2": node("CLIPLoader", clip_name=spec.encoder, type=spec.clip_type,
                  device="cpu" if model == "nvfp4" else "default"),
        "3": node("VAELoader", vae_name=spec.vae),
        "4": node("CLIPTextEncode", clip=["2", 0], text=prompt),
        "11": node("VAEDecode", samples=["10", 0], vae=["3", 0]),
        "12": node("SaveImage", images=["11", 0], filename_prefix=f"ImageMagic/{run_id}"),
    }
    if external_session:
        graph["12"] = node("ImageMagicSaveSessionImage", images=["11", 0], session_id=external_session, run_id=run_id)
    if model == "z-image-turbo":
        if source:
            raise ValueError("Z-Image-Turbo generates originals. Use Klein for instruction edits.")
        graph.update({
            "5": node("EmptySD3LatentImage", width=1024, height=1024, batch_size=1),
            "6": node("ModelSamplingAuraFlow", model=["1", 0], shift=3.0),
            "7": node("ConditioningZeroOut", conditioning=["4", 0]),
            "10": node("KSampler", model=["6", 0], positive=["4", 0], negative=["7", 0],
                       latent_image=["5", 0], seed=seed, steps=8, cfg=1.0,
                       sampler_name="res_multistep", scheduler="simple", denoise=1.0),
        })
        return graph

    graph.update({
        "5": node("EmptyFlux2LatentImage", width=1024, height=1024, batch_size=1),
        "6": node("RandomNoise", noise_seed=seed),
        "7": node("KSamplerSelect", sampler_name="euler"),
        "8": node("Flux2Scheduler", steps=50 if model == "base" else 4, width=1024, height=1024),
        "9": node("BasicGuider", model=["1", 0], conditioning=["4", 0]),
        "10": node("SamplerCustomAdvanced", noise=["6", 0], guider=["9", 0], sampler=["7", 0],
                   sigmas=["8", 0], latent_image=["5", 0]),
    })
    if model == "base":
        graph["13"] = node("CLIPTextEncode", clip=["2", 0], text="")
        graph["9"] = node("CFGGuider", model=["1", 0], positive=["4", 0], negative=["13", 0], cfg=4.0)
    if source:
        graph["14"] = node("LoadImage", image=f"ImageMagic/{source} [output]")
        if external_session:
            graph["14"] = node("ImageMagicLoadSessionImage", session_id=external_session, filename=source)
        graph["15"] = node("VAEEncode", pixels=["14", 0], vae=["3", 0])
        graph["16"] = node("ReferenceLatent", conditioning=["4", 0], latent=["15", 0])
        if model == "base":
            graph["17"] = node("ReferenceLatent", conditioning=["13", 0], latent=["15", 0])
            graph["9"]["inputs"].update(positive=["16", 0], negative=["17", 0])
        else:
            graph["9"]["inputs"]["conditioning"] = ["16", 0]
    return graph


routes = PromptServer.instance.routes
# Keep deletion and the handoff of new jobs to ComfyUI's queue mutually exclusive.
queue_lock = asyncio.Lock()


def find_session(session_id):
    try:
        return catalog.get(session_id)
    except KeyError:
        raise web.HTTPNotFound(text="Session not found.")


def session_folder(session):
    if session.id == "previous":
        return OUTPUT
    try:
        return session.require_folder()
    except FolderUnavailable as error:
        raise web.HTTPConflict(text=str(error))


@routes.get("/studio")
async def studio(request):
    sessions = catalog.sessions()
    if next(iter_gallery_images(OUTPUT), None) or trash_snapshot(OUTPUT.resolve() / ".trash")[0]:
        sessions.append(catalog.get("previous"))
    rows = []
    for session in sessions:
        name = escape(session.name)
        if session.available():
            rows.append(f'<li><a href="/studio/session/{session.id}"><span>{name}</span>'
                        f'<span aria-hidden="true">→</span></a><button class="delete-link" '
                        f'data-session="{session.id}" aria-label="Delete {name}" aria-haspopup="dialog">Delete</button></li>')
        else:
            rows.append(f'<li class="offline"><span>{name}</span>'
                        f'<small>Folder unavailable · {escape(str(session.folder))}</small></li>')
    contents = f'<ul class="session-list">{"".join(rows)}</ul>' if rows else '<p class="empty-list">No sessions yet.</p>'
    page = (ROOT / "sessions.html").read_text(encoding="utf-8").replace("{{sessions}}", contents)
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


def session_name(name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise web.HTTPBadRequest(text="Enter a session name between 1 and 80 characters.")
    return name.strip()


def require_local_form(request):
    if (request.remote not in {"127.0.0.1", "::1"} or request.url.host not in {"localhost", "127.0.0.1", "::1"}
            or request.headers.get("Origin") != str(request.url.origin())):
        raise web.HTTPForbidden(text="Choose a save location from the local ImageMagic window.")


picker_lock = asyncio.Lock()


@routes.post("/studio/api/choose-folder")
async def choose_folder(request):
    require_local_form(request)
    name = session_name((await request.json()).get("name"))
    if picker_lock.locked():
        raise web.HTTPConflict(text="A folder chooser is already open.")
    async with picker_lock:
        # The browser cannot supply an absolute Windows path from a directory upload.
        command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object Windows.Forms.FolderBrowserDialog; "
            "$d.Description='Choose where to create the ImageMagic session folder'; "
            "$owner=New-Object Windows.Forms.Form; $owner.TopMost=$true; "
            "try { if($d.ShowDialog($owner) -eq 'OK'){"
            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
            "[Console]::Write($d.SelectedPath)} } finally {$d.Dispose(); $owner.Dispose()}"
        )
        process = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-STA", "-Command", command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW)
        data, _ = await process.communicate()
        if process.returncode:
            raise web.HTTPConflict(text="The Windows folder chooser could not open.")
        try:
            destination = catalog.suggest(Path(data.decode("utf-8")), name) if data else None
        except OSError as error:
            raise web.HTTPConflict(text=f"The selected folder is unavailable. {error}")
        return web.json_response({"destination": str(destination) if destination else None})


@routes.post("/studio/sessions")
async def create_session(request):
    form = await request.post()
    name = session_name(form.get("name"))
    destination = form.get("destination") or None
    if destination:
        require_local_form(request)
    try:
        session = catalog.create(name, destination)
    except FileExistsError:
        raise web.HTTPConflict(text="This folder already exists. Choose the location again for a new folder name.")
    except (OSError, ValueError) as error:
        raise web.HTTPBadRequest(text=f"Could not create the session folder. {error}")
    raise web.HTTPSeeOther(location=f"/studio/session/{session.id}")


@routes.get("/studio/session/{session_id}")
async def open_session(request):
    session = find_session(request.match_info["session_id"])
    session_folder(session)
    page = (ROOT / "studio.html").read_text(encoding="utf-8").replace("{{session_name}}", escape(session.name))
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


@routes.get("/studio/style.css")
async def stylesheet(request):
    return web.FileResponse(ROOT / "style.css")


@routes.get("/studio/favicon.svg")
async def favicon(request):
    return web.FileResponse(ROOT / "favicon.svg", headers={"Content-Type": "image/svg+xml"})


@routes.get("/studio/api/models")
async def models(request):
    return web.json_response(installed_models())


@routes.post("/studio/api/generate")
async def generate(request):
    body = await request.json()
    async with queue_lock:
        session = find_session(body.get("session", "previous"))
        return await submit(request, body.get("prompt"), body.get("model", "fp8"), session=session, seed=body.get("seed"))


@routes.post("/studio/api/edit")
async def edit(request):
    body = await request.json()
    async with queue_lock:
        return await queue_edit(request, body)


async def queue_edit(request, body):
    source = body.get("source")
    if not isinstance(source, str) or not IMAGE_NAME.fullmatch(source):
        raise web.HTTPBadRequest(text="Choose an image from the studio gallery.")
    session = find_session(body.get("session", "previous"))
    path = session_folder(session) / source
    try:
        parent = image_info(path, path.stat().st_mtime)
        if session.custom and parent.get("session_id") != session.id:
            raise ValueError("Image belongs to another session.")
    except (OSError, ValueError, KeyError):
        raise web.HTTPNotFound(text="The selected image is no longer available.")
    model = parent.get("model_id")
    if model is None:  # Older studio PNGs store only the display name.
        model = next((key for key, spec in MODELS.items() if spec.label == parent["model"]), None)
    if model in MODELS and MODELS[model].edit_with:
        model = MODELS[model].edit_with
        if model not in installed_models():
            raise web.HTTPBadRequest(text=f"Install {MODELS[model].label} to edit this image.")
    return await submit(request, body.get("prompt"), model, parent, session=session)


async def submit(request, prompt, model, parent=None, *, session, seed=None):
    folder = session_folder(session)
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not prompt or len(prompt) > 8000 or not isinstance(model, str) or model not in installed_models():
        raise web.HTTPBadRequest(text="Enter a prompt and choose an installed model.")
    run_id = uuid.uuid4().hex
    if seed is None:
        seed = secrets.randbits(52)
    elif type(seed) is not int or not 0 <= seed < 2**53:
        raise web.HTTPBadRequest(text="Use a nonnegative seed below 2^53.")
    info = {"prompt": prompt, "model": MODELS[model].label, "model_id": model,
            "seed": seed, "submitted": time.time()}
    source = None
    if parent:
        source = parent["file"]
        info.update(parent=source, original=parent.get("original", source))
    relative = Path() if session.custom else folder.relative_to(OUTPUT)
    if session.custom:
        info["session_id"] = session.id
    output_prefix = (relative / run_id).as_posix()
    reference = (relative / source).as_posix() if source else None
    payload = {"prompt": workflow(prompt, model, seed, output_prefix, reference,
                                  external_session=session.id if session.custom else None),
               "extra_data": {"extra_pnginfo": {"imagemagic": info}}}
    port = request.transport.get_extra_info("sockname")[1]
    async with ClientSession() as session:
        async with session.post(f"http://127.0.0.1:{port}/prompt", json=payload) as result:
            return web.Response(body=await result.read(), status=result.status, content_type="application/json")


def image_info(path, modified):
    if path.resolve(strict=True) != path:
        raise ValueError("Invalid image location.")
    return cached_image_info(path, modified)


@lru_cache(maxsize=2048)
def cached_image_info(path, modified):
    with Image.open(path) as image:
        info = json.loads(image.info["imagemagic"])
    model = MODELS.get(info.get("model_id"))
    if model and model.edit_with:
        info["edit_model_label"] = MODELS[model.edit_with].label
    subfolder = None
    if path.is_relative_to(OUTPUT):
        subfolder = path.parent.relative_to(OUTPUT.parent).as_posix()
    return {**info, "file": path.name, "subfolder": subfolder,
            "seconds": round(max(0, modified - info["submitted"]), 1)}


def iter_gallery_images(folder, *, require_readable=False, owner=None):
    for path in folder.glob("*.png"):
        try:
            item = image_info(path, path.stat().st_mtime)
            if owner is None or (item.get("session_id") == owner and IMAGE_NAME.fullmatch(path.name)):
                yield item
        except (Image.UnidentifiedImageError, ValueError, KeyError):
            continue
        except OSError:
            if require_readable:
                raise


def gallery_images(session):
    items = iter_gallery_images(session_folder(session), owner=session.id if session.custom else None)
    return sorted(items, key=lambda item: item["submitted"], reverse=True)


@routes.get("/studio/api/gallery")
async def gallery(request):
    session = find_session(request.query.get("session", "previous"))
    return web.json_response(gallery_images(session), headers={"Cache-Control": "no-store"})


@routes.get("/studio/api/sessions/{session_id}/images/{filename}")
async def session_image(request):
    session = find_session(request.match_info["session_id"])
    filename = request.match_info["filename"]
    if not session.custom or not IMAGE_NAME.fullmatch(filename):
        raise web.HTTPNotFound()
    path = session_folder(session) / filename
    try:
        if image_info(path, path.stat().st_mtime).get("session_id") != session.id:
            raise ValueError("Image belongs to another session.")
    except (OSError, KeyError, ValueError):
        raise web.HTTPNotFound()
    return web.FileResponse(path)


def trash_directory(folder):
    trash = folder / ".trash"
    if trash.resolve() != trash:
        raise web.HTTPBadRequest(text="Invalid gallery trash location.")
    return trash


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
    session = find_session(body.get("session", "previous"))
    async with queue_lock:
        folder = session_folder(session)
        running, queued = PromptServer.instance.prompt_queue.get_current_queue_volatile()
        items = gallery_images(session)
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
                inputs = node.get("inputs", {})
                if (node.get("class_type") == "ImageMagicLoadSessionImage" and inputs.get("session_id") == session.id
                        and inputs.get("filename") in filenames):
                    raise web.HTTPConflict(text="An edit is using this image. Try again when it finishes.")
                source = inputs.get("image")
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


def trash_snapshot(trash, owner=None):
    images = []
    for batch in trash_batches(trash):
        if owner:
            images.extend(batch / item["file"] for item in iter_gallery_images(batch, owner=owner, require_readable=True))
        else:
            images.extend(path for path in batch.glob("*.png") if path.resolve() == path and path.is_file())
    names = sorted(path.relative_to(trash).as_posix() for path in images)
    revision = hashlib.sha256(json.dumps(names).encode()).hexdigest()
    return images, revision


def purge_images(images, trash):
    for image in images:
        if image.resolve() != image:
            raise web.HTTPConflict(text="The files have changed. Review them again.")
        image.unlink(missing_ok=True)
    for directory in [*trash_batches(trash), trash]:
        if directory.resolve() == directory and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def session_in_queue(session):
    destination = None if session.custom else PurePosixPath(session.folder.relative_to(OUTPUT.parent).as_posix())
    running, queued = PromptServer.instance.prompt_queue.get_current_queue_volatile()
    for job in (*running, *queued):
        for node in job[2].values():
            inputs = node.get("inputs", {})
            if session.custom:
                if (node.get("class_type") in {"ImageMagicSaveSessionImage", "ImageMagicLoadSessionImage"}
                        and inputs.get("session_id") == session.id):
                    return True
                continue
            if node.get("class_type") == "SaveImage":
                path = inputs.get("filename_prefix")
            elif node.get("class_type") == "LoadImage":
                path = inputs.get("image")
                if not isinstance(path, str) or not path.endswith(" [output]"):
                    continue
                path = path.removesuffix(" [output]")
            else:
                continue
            if isinstance(path, str) and PurePosixPath(path.replace("\\", "/")).parent == destination:
                return True
    return False


def session_deletion_snapshot(session):
    folder = session_folder(session)
    owner = session.id if session.custom else None
    trash = trash_directory(folder)
    saved = [folder / item["file"] for item in iter_gallery_images(folder, require_readable=True, owner=owner)]
    discarded, _ = trash_snapshot(trash, owner)
    files = saved + discarded
    entries = []
    for path in files:
        if path.resolve() != path:
            raise web.HTTPConflict(text="A session image points outside its folder. Check its location first.")
        stat = path.stat()
        entries.append((path.relative_to(trash.parent).as_posix(), stat.st_size, stat.st_mtime_ns))
    revision = hashlib.sha256(json.dumps([folder.name, sorted(entries)]).encode()).hexdigest()
    return {"images": len(saved), "trashed": len(discarded), "revision": revision, "folder": str(folder)}, files, trash


@routes.get("/studio/api/sessions/{session_id}/deletion")
async def preview_session_deletion(request):
    session = find_session(request.match_info["session_id"])
    try:
        info, _, _ = session_deletion_snapshot(session)
    except OSError as error:
        raise web.HTTPConflict(text="Could not count all the images. Check the files and try again.") from error
    return web.json_response(info, headers={"Cache-Control": "no-store"})


@routes.post("/studio/api/sessions/{session_id}/delete")
async def delete_session(request):
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("revision"), str):
        raise web.HTTPBadRequest(text="Review the image count before deleting this session.")
    async with queue_lock:
        session = find_session(request.match_info["session_id"])
        if session_in_queue(session):
            raise web.HTTPConflict(text="This session has a queued or running job. Try again when it finishes.")
        try:
            info, files, trash = session_deletion_snapshot(session)
            if body["revision"] != info["revision"]:
                raise web.HTTPConflict(text="The contents of this session have changed.")
            purge_images(files, trash)
            catalog.remove(session)
        except OSError as error:
            raise web.HTTPConflict(text="Could not finish deleting the session. Check the remaining files and try again.") from error
    return web.json_response({"deleted": len(files)})


@routes.get("/studio/api/trash")
async def trash_info(request):
    session = find_session(request.query.get("session", "previous"))
    images, revision = trash_snapshot(trash_directory(session_folder(session)), session.id if session.custom else None)
    return web.json_response({"count": len(images), "revision": revision}, headers={"Cache-Control": "no-store"})


@routes.post("/studio/api/trash/empty")
async def empty_trash(request):
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("revision"), str) or "session" not in body:
        raise web.HTTPBadRequest(text="Choose a session and confirm what is in its trash.")
    session = find_session(body["session"])
    trash = trash_directory(session_folder(session))
    # Scanning and unlinking are synchronous, so studio requests cannot interleave here.
    images, revision = trash_snapshot(trash, session.id if session.custom else None)
    if body["revision"] != revision:
        raise web.HTTPConflict(text="The trash has changed. Choose Empty trash again to review it.")
    try:
        purge_images(images, trash)
    except OSError as error:
        raise web.HTTPConflict(text="Could not finish emptying the trash. Check the remaining files and try again.") from error
    return web.json_response({"deleted": len(images)})
