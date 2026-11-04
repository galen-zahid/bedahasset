"""Lazy model registry, loaded once per batch. Picks GPU when available."""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger("split")


def pick_device(pref: str = "auto") -> str:
    import torch

    if pref == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if pref == "cuda":
        log.warning("CUDA diminta tapi tidak tersedia -> pakai CPU")
    return "cpu"


def _cached(loader, name):
    """Load a HuggingFace model from the local cache first (no network round-trips, no rate
    limits); only download when it is not cached yet."""
    try:
        return loader(name, local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet
        return loader(name)


class Models:
    def __init__(self, cfg):
        self.cfg = cfg
        self.device = pick_device(cfg.get("device", "auto"))
        log.info("device: %s", self.device)
        self._rembg = None
        self._depth = None
        self._ocr = None
        self._lama = None
        self._clipseg = None

    # ---------------------------------------------------------------- rembg
    def salient_mask(self, rgb_u8: np.ndarray) -> np.ndarray:
        """Return soft mask float32 0..1 of the main subject."""
        from PIL import Image
        from rembg import new_session, remove

        if self._rembg is None:
            providers = ["CPUExecutionProvider"]
            if self.device == "cuda":
                import onnxruntime as ort

                if "CUDAExecutionProvider" in ort.get_available_providers():
                    providers.insert(0, "CUDAExecutionProvider")
            self._rembg = new_session(self.cfg.subject.rembg_model, providers=providers)
        m = remove(Image.fromarray(rgb_u8), session=self._rembg, only_mask=True,
                   post_process_mask=False)
        return np.asarray(m, dtype=np.float32) / 255.0

    # ---------------------------------------------------------------- depth
    def depth(self, rgb_u8: np.ndarray) -> np.ndarray:
        """Relative depth normalized 0..1, 1 = nearest to camera. Same HxW as input."""
        import cv2
        from PIL import Image
        from transformers import pipeline

        if self._depth is None:
            self._depth = _cached(
                lambda name, **kw: pipeline("depth-estimation", model=name,
                                            device=0 if self.device == "cuda" else -1,
                                            model_kwargs=kw),
                self.cfg.foreground.depth_model)
        out = self._depth(Image.fromarray(rgb_u8))
        d = np.asarray(out["predicted_depth"], dtype=np.float32).squeeze()
        d = cv2.resize(d, (rgb_u8.shape[1], rgb_u8.shape[0]), interpolation=cv2.INTER_CUBIC)
        lo, hi = np.percentile(d, 0.5), np.percentile(d, 99.5)
        return np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)

    # ------------------------------------------------------------------ ocr
    @property
    def ocr(self):
        if self._ocr is None:
            import easyocr

            self._ocr = easyocr.Reader(list(self.cfg.text.languages),
                                       gpu=self.device == "cuda", verbose=False)
        return self._ocr

    # -------------------------------------------------------------- clipseg
    def text_seg(self, rgb_u8: np.ndarray, prompts) -> np.ndarray:
        """CLIPSeg: max probability over text prompts, resized to HxW (coarse, 352px)."""
        import cv2
        import torch
        from PIL import Image
        from transformers import CLIPSegForImageSegmentation, CLIPSegProcessor

        if self._clipseg is None:
            name = self.cfg.particles.cloud.model
            proc = _cached(CLIPSegProcessor.from_pretrained, name)
            model = _cached(CLIPSegForImageSegmentation.from_pretrained, name)
            self._clipseg = (proc, model.to(self.device).eval())
        proc, model = self._clipseg
        im = Image.fromarray(rgb_u8)
        inp = proc(text=list(prompts), images=[im] * len(prompts), return_tensors="pt", padding=True)
        inp = {k: v.to(self.device) for k, v in inp.items()}
        with torch.no_grad():
            p = torch.sigmoid(model(**inp).logits).cpu().numpy()
        p = p.reshape(len(prompts), *p.shape[-2:]).max(0)
        return cv2.resize(p, (rgb_u8.shape[1], rgb_u8.shape[0]), interpolation=cv2.INTER_CUBIC)

    # ----------------------------------------------------------------- lama
    def inpaint(self, rgb_u8: np.ndarray, mask_u8: np.ndarray) -> np.ndarray:
        import torch
        from simple_lama_inpainting import SimpleLama

        if self._lama is None:
            self._lama = SimpleLama(device=torch.device(self.device))
        h, w = mask_u8.shape
        out = np.asarray(self._lama(rgb_u8, mask_u8))
        return out[:h, :w, :3]  # LaMa pads to multiple of 8
