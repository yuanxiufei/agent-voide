# -*- coding: utf-8 -*-
"""图像生成 Provider 抽象层（蓝图 §二十二「未来模型适配」）。

    「系统不要绑定单一图片模型。Prompt Agent 输出统一格式，
      由 Provider 决定具体 API。」

内置
────
  mock      —— **零依赖**（zlib+struct 手写 PNG），产出真实可打开的占位图。
               目的：让整条流水线在**没有任何 API Key 的电脑上也能跑通**。
  openai    —— OpenAI 兼容 `POST {base_url}/images/generations`
               （OpenAI / 智谱 CogView / 通义万相兼容模式 / 各类网关）
  stability —— Stability AI `stable-image/generate/core`

依赖策略
────────
  mock 只用标准库 → **装完 Python 就能跑**；
  openai / stability 需要 requests，**只在真正调用时 import** →
  没装也不影响 mock，不会因缺依赖导致项目起不来。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import urllib.request
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass


# ── 手写 PNG（零依赖）──

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: str, width: int, height: int, pixel_fn) -> None:
    """把 `pixel_fn(x, y) -> (r, g, b)` 写成 PNG。纯标准库，无需 Pillow。"""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        row = bytearray()
        for x in range(width):
            r, g, b = pixel_fn(x, y)
            row += bytes((r & 255, g & 255, b & 255))
        raw += row
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + _chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)


def png_size(path: str) -> tuple[int, int] | tuple[None, None]:
    """读 PNG 的宽高（只读头部，不解码全图）。

    用途：核验产出图是否真是**预期尺寸**（尺寸错了多半是 Provider 参数没生效）。
    ⚠️ 只支持 PNG —— 本项目只用 PNG。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
            return None, None
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        return w, h
    except Exception:                                                # noqa: BLE001
        return None, None


@dataclass
class ProviderInfo:
    name: str
    available: bool
    reason: str = ""
    needs_key: bool = True


class ImageProvider(ABC):
    name = "base"

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}

    @abstractmethod
    def generate(self, *, prompt: str, negative_prompt: str = "",
                 width: int = 1024, height: int = 1024,
                 out_path: str = "", n: int = 1) -> list[str]:
        ...

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, True)


class MockProvider(ImageProvider):
    """不调用网络，手写一张**真实可打开的 PNG**。

    为什么不是「返回假路径」：那样下游看不到图，无法验证落盘与预览链路。
    这里产出的是真图 —— 按资产 ID 派生配色，并画出 16:9 资产图的版式提示
    （左 32% 分隔线 = 特写区，右侧三条三分线 = 三视图区）。

    ⚠️ **性能**：朴素实现是「逐像素调函数」（1024×576 = 59 万次 Python 调用），
    实测慢到不可接受（命令行会卡住）。故改为：
      ① 先算**低分辨率图案**（≈ 256×144）
      ② **最近邻放大**，并用「行缓存 + `bytes * n`」避免逐像素拼接
      ③ 版式线在**最终分辨率**上以整行/整列赋值叠加
    结果：像素计算量降约 16 倍，且无逐像素 Python 循环。
    """

    name = "mock"

    def generate(self, *, prompt: str, negative_prompt: str = "",
                 width: int = 1024, height: int = 1024,
                 out_path: str = "", n: int = 1) -> list[str]:
        seed = hashlib.sha256((prompt + negative_prompt).encode("utf-8")).digest()
        base = (seed[0], seed[1], seed[2])
        accent = (seed[3], seed[4], seed[5])
        gray = bytes((245, 245, 245))
        edge = bytes((30, 30, 30))

        scale = max(1, (width + 255) // 256)          # 放大倍数
        bw, bh = max(1, width // scale), max(1, height // scale)

        # ① 低分辨率渐变
        small: list[bytes] = []
        for y in range(bh):
            fy = y / max(1, bh - 1)
            row = bytearray()
            for x in range(bw):
                t = (x / max(1, bw - 1)) * 0.6 + fy * 0.4
                row += bytes((int(base[0] * (1 - t) + accent[0] * t),
                              int(base[1] * (1 - t) + accent[1] * t),
                              int(base[2] * (1 - t) + accent[2] * t)))
            small.append(bytes(row))

        # ② 放大（行缓存 —— 同一源行只拼一次）
        row_cache: dict[int, bytearray] = {}
        for sy in range(bh):
            row = bytearray()
            srow = small[sy]
            for x in range(bw):
                row += srow[x * 3:x * 3 + 3] * scale
            row_cache[sy] = row

        # ③ 叠加版式线（最终分辨率）
        thirds_x = (width // 3, 2 * width // 3)
        thirds_y = (height // 3, 2 * height // 3)
        split_x = int(width * 0.32)
        raw = bytearray()
        for y in range(height):
            sy = min(y // scale, bh - 1)
            if y < 2 or y >= height - 2 or y in thirds_y:
                row = bytearray(edge if y < 2 or y >= height - 2
                                else bytes((200, 210, 220)) * width)
            else:
                row = bytearray(row_cache[sy])
            for cx in (split_x,) + thirds_x:
                row[cx * 3:cx * 3 + 3] = gray
            raw.append(0)                              # filter type
            raw += row

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        blob = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
                + _chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + _chunk(b"IEND", b""))

        paths = []
        for i in range(max(1, n)):
            p = out_path if n == 1 else f"{os.path.splitext(out_path)[0]}_{i + 1}.png"
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
            with open(p, "wb") as f:
                f.write(blob)
            paths.append(p)
        return paths

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, True,
                            "零依赖占位图（不调网络，用于验证流水线）", needs_key=False)


class OpenAICompatProvider(ImageProvider):
    name = "openai"

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        self.api_key = (self.cfg.get("api_key") or os.getenv("IMAGE_API_KEY")
                        or os.getenv("OPENAI_API_KEY") or "")
        self.base_url = (self.cfg.get("base_url") or os.getenv("IMAGE_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.model = self.cfg.get("model") or os.getenv("IMAGE_MODEL") or "gpt-image-1"

    def generate(self, *, prompt: str, negative_prompt: str = "",
                 width: int = 1024, height: int = 1024,
                 out_path: str = "", n: int = 1) -> list[str]:
        if not self.api_key:
            raise RuntimeError("缺少 API Key：请设置环境变量 IMAGE_API_KEY")
        try:
            import requests
        except ImportError as e:
            raise RuntimeError("需要 requests：pip install requests") from e

        full = prompt
        if negative_prompt:
            # 部分兼容网关不认 negative 字段 → 併入正文，保证约束不丢
            full = f"{prompt}\n\nAvoid: {negative_prompt}"
        resp = requests.post(
            f"{self.base_url}/images/generations",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json={"model": self.model, "prompt": full,
                  "size": f"{width}x{height}", "n": n},
            timeout=self.cfg.get("timeout", 300))
        resp.raise_for_status()
        data = resp.json()

        paths = []
        for i, item in enumerate(data.get("data", [])):
            p = out_path if n == 1 else f"{os.path.splitext(out_path)[0]}_{i + 1}.png"
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
            if item.get("b64_json"):
                with open(p, "wb") as f:
                    f.write(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                with urllib.request.urlopen(item["url"], timeout=300) as r:
                    with open(p, "wb") as f:
                        f.write(r.read())
            else:
                raise RuntimeError(f"响应无图像数据：{json.dumps(item)[:200]}")
            paths.append(p)
        if not paths:
            raise RuntimeError(f"响应无图像数据：{json.dumps(data)[:300]}")
        return paths

    def info(self) -> ProviderInfo:
        if not self.api_key:
            return ProviderInfo(self.name, False, "未设置 IMAGE_API_KEY")
        return ProviderInfo(self.name, True, f"{self.base_url} · {self.model}")


class StabilityProvider(ImageProvider):
    name = "stability"

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        self.api_key = self.cfg.get("api_key") or os.getenv("IMAGE_API_KEY") or ""
        self.base_url = (self.cfg.get("base_url") or "https://api.stability.ai").rstrip("/")
        self.model = self.cfg.get("model") or "core"

    def generate(self, *, prompt: str, negative_prompt: str = "",
                 width: int = 1024, height: int = 1024,
                 out_path: str = "", n: int = 1) -> list[str]:
        if not self.api_key:
            raise RuntimeError("缺少 API Key：请设置环境变量 IMAGE_API_KEY")
        try:
            import requests
        except ImportError as e:
            raise RuntimeError("需要 requests：pip install requests") from e
        paths = []
        for i in range(max(1, n)):
            p = out_path if n == 1 else f"{os.path.splitext(out_path)[0]}_{i + 1}.png"
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
            resp = requests.post(
                f"{self.base_url}/v2beta/stable-image/generate/{self.model}",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Accept": "image/*"},
                files={"none": ""},
                data={"prompt": prompt, "negative_prompt": negative_prompt,
                      "aspect_ratio": _closest_aspect(width, height),
                      "output_format": "png"},
                timeout=self.cfg.get("timeout", 300))
            resp.raise_for_status()
            with open(p, "wb") as f:
                f.write(resp.content)
            paths.append(p)
        return paths

    def info(self) -> ProviderInfo:
        if not self.api_key:
            return ProviderInfo(self.name, False, "未设置 IMAGE_API_KEY")
        return ProviderInfo(self.name, True, f"{self.base_url} · {self.model}")


def _closest_aspect(w: int, h: int) -> str:
    choices = {"16:9": 16 / 9, "1:1": 1.0, "3:2": 1.5, "9:16": 9 / 16, "2:3": 2 / 3}
    target = w / h if h else 1
    return min(choices, key=lambda k: abs(choices[k] - target))


PROVIDERS: dict[str, type[ImageProvider]] = {
    "mock": MockProvider, "openai": OpenAICompatProvider,
    "stability": StabilityProvider,
}


def get_provider(name: str, cfg: dict | None = None) -> ImageProvider:
    if name not in PROVIDERS:
        raise ValueError(f"未知 provider：{name}（可选 {list(PROVIDERS)}）")
    return PROVIDERS[name](cfg)


def list_providers(cfg: dict | None = None) -> list[ProviderInfo]:
    return [cls(cfg).info() for cls in PROVIDERS.values()]
