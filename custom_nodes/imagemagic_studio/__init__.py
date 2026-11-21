"""Local prompt gallery for the installed FLUX.2 Klein checkpoints."""
import json
import re
import secrets
import time
import uuid
from functools import lru_cache
from pathlib import Path

from aiohttp import ClientSession, web
from PIL import Image
import folder_paths
from server import PromptServer

NODE_CLASS_MAPPINGS = {}
ROOT = Path(__file__).parent
OUTPUT = Path(folder_paths.get_output_directory()) / "ImageMagic"
MODELS = {
    "fp8": ("Klein 4B · FP8", "flux-2-klein-4b-fp8.safetensors"),
    "nvfp4": ("Klein 4B · Compact", "flux-2-klein-4b-nvfp4.safetensors"),
    "base": ("Klein 4B Base · FP8", "flux-2-klein-base-4b-fp8.safetensors"),
}


def workflow(prompt, model, seed, run_id, source=None):
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}

    graph = {
        "1": node("UNETLoader", unet_name=MODELS[model][1], weight_dtype="default"),
        "2": node("CLIPLoader", clip_name="qwen_3_4b.safetensors", type="flux2",
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


@routes.get("/studio")
async def studio(request):
    return web.FileResponse(ROOT / "studio.html")


@routes.get("/studio/api/models")
async def models(request):
    installed = folder_paths.get_filename_list("diffusion_models")
    return web.json_response({k: v[0] for k, v in MODELS.items() if v[1] in installed})


@routes.post("/studio/api/generate")
async def generate(request):
    body = await request.json()
    return await submit(request, body.get("prompt"), body.get("model", "fp8"))


@routes.post("/studio/api/edit")
async def edit(request):
    body = await request.json()
    source = body.get("source")
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{32}_\d+_\.png", source):
        raise web.HTTPBadRequest(text="Choose an image from the studio gallery.")
    path = OUTPUT / source
    try:
        parent = image_info(path, path.stat().st_mtime)
    except (OSError, ValueError, KeyError):
        raise web.HTTPNotFound(text="The selected image is no longer available.")
    model = next((key for key, (name, _) in MODELS.items() if name == parent["model"]), None)
    return await submit(request, body.get("prompt"), model, parent)


async def submit(request, prompt, model, parent=None):
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not prompt or len(prompt) > 8000 or model not in MODELS:
        raise web.HTTPBadRequest(text="Enter a prompt and choose an installed model.")
    run_id = uuid.uuid4().hex
    seed = secrets.randbits(52)
    info = {"prompt": prompt, "model": MODELS[model][0], "seed": seed, "submitted": time.time()}
    source = None
    if parent:
        source = parent["file"]
        info.update(parent=source, original=parent.get("original", source))
    payload = {"prompt": workflow(prompt, model, seed, run_id, source),
               "extra_data": {"extra_pnginfo": {"imagemagic": info}}}
    port = request.transport.get_extra_info("sockname")[1]
    async with ClientSession() as session:
        async with session.post(f"http://127.0.0.1:{port}/prompt", json=payload) as result:
            return web.Response(body=await result.read(), status=result.status, content_type="application/json")


@lru_cache(maxsize=2048)
def image_info(path, modified):
    with Image.open(path) as image:
        info = json.loads(image.info["imagemagic"])
    return {**info, "file": path.name, "seconds": round(max(0, modified - info["submitted"]), 1)}


@routes.get("/studio/api/gallery")
async def gallery(request):
    items = []
    for path in OUTPUT.glob("*.png"):
        try:
            items.append(image_info(path, path.stat().st_mtime))
        except (OSError, ValueError, KeyError):
            continue
    return web.json_response(sorted(items, key=lambda item: item["submitted"], reverse=True),
                             headers={"Cache-Control": "no-store"})
