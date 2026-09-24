# -*- coding: utf-8 -*-
"""主 Agent —— 把各层编排成一条流水线（蓝图 §二十三 最终目标）。

    自然语言
        ↓
    Router（意图/类型）          router.py
        ↓
    解析（规则 或 LLM）          nl_parser.py / llm_client.py
        ↓
    补全（题材预设 或 LLM）       character_agent / prop_agent / costume_agent
        ↓
    结构化资产卡                 schema.py
        ↓
    Prompt Engine（中英 + 负面词） prompt_engine.py ← RuleSource（工作流权威规则）
        ↓
    Consistency Gate             consistency.py
        ↓
    Image Provider               image_provider.py（mock 零依赖 / openai / stability）
        ↓
    落盘 + 版本 + 元数据          asset_manager.py
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import (batch as batch_mod, character_agent, costume_agent,
               expression_agent, pose_agent, prop_agent, prompt_engine, scene_agent)
from .asset_manager import AssetManager, now_str
from .consistency import (ConsistencyReport, check_modify_scope, check_required,
                          check_text_risk, full_check, text_risk_checklist)
from . import lock
from .image_provider import get_provider, png_size
from .llm_client import LLMClient
from .prompt_engine import build_prompts, name_suppressed_note
from .router import route
from .rule_source import RuleSource
from .schema import AssetCard, parse_id

# ⭐ 六类资产各有一个 agent（与 `schema.ASSET_TYPE_CN` 的键一一对应）。
#    新增一类资产 = 这里加一行 + `registry.py` 的 asset agent 输出里加一项。
#    ⚠️ 曾漏 environment/expression/pose → 那三类会**静默回退成角色 agent**
#       （补出一套角色字段，用户拿到的是错的资产卡）。
AGENTS = {
    "character": character_agent,
    "costume": costume_agent,
    "prop": prop_agent,
    "environment": scene_agent,      # ENV_ 场景
    "expression": expression_agent,  # EXP_ 表情集
    "pose": pose_agent,              # POS_ 动作集
}


# 查询时「对象名词 → 资产类型」（比路由触发词更具体，见 `_query`）
_OBJECT_TYPE: list[tuple[tuple[str, ...], str]] = [
    (("武器", "刀", "枪", "剑", "装置", "道具", "装备", "护甲"), "prop"),
    (("服装", "衣服", "套装", "制服", "战衣", "风衣", "盔甲", "长袍"), "costume"),
    (("场景", "环境", "建筑", "地图"), "environment"),
    (("表情", "表情集", "神态"), "expression"),
    (("动作", "姿势", "姿态", "动作集"), "pose"),
    (("角色", "人物", "主角", "配角", "NPC"), "character"),
]


def _type_from_object(text: str) -> str:
    """从输入里的**对象名词**推断资产类型；推断不出返回空串。"""
    for words, t in _OBJECT_TYPE:
        if any(w in text for w in words):
            return t
    return ""


def _set_pair(vd, fld: str, cn_value: str) -> None:
    """同时写中文值与其**英文伴生字段**。

    ⚠️ 只写中文会让英文 prompt 落到 `tr()` 兜底翻译 —— 词表没覆盖的词
    （如「及腰」变体、「系」后缀）会原样留在英文 prompt 里。
    """
    from .prompt_engine import tr
    setattr(vd, fld, cn_value)
    setattr(vd, fld + "_en", tr(cn_value))


@dataclass
class AgentConfig:
    root: Path
    provider: str = "mock"
    width: int = 1024
    height: int = 576          # 16:9
    image_cfg: dict = field(default_factory=dict)
    llm_cfg: dict = field(default_factory=dict)
    id_style: str = "project"
    workflow_root: str = ""
    generate: bool = True
    # 显式参考图（`--reference`）：任意生成都能挂一张基图做图生图。
    # 六角度的铁则②会自动设它，这里是给用户的通用入口。
    reference_image: str = ""

    @classmethod
    def load(cls, root: str | Path) -> "AgentConfig":
        root = Path(root)
        cfg_file = root / "config.json"
        data = {}
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"⚠️ config.json 解析失败，用默认值：{e}")
        img = data.get("image", {}) or {}
        return cls(
            root=root,
            provider=img.get("provider", "mock"),
            width=int(img.get("width", 1024)),
            height=int(img.get("height", 576)),
            image_cfg=img,
            llm_cfg=data.get("llm", {}) or {},
            id_style=(data.get("id_style") or "project"),
            workflow_root=(data.get("workflow", {}) or {}).get("root", ""),
            generate=bool(data.get("generate_images", True)),
        )


class DramaAssetAgent:
    def __init__(self, cfg: AgentConfig | None = None):
        self.root = Path(cfg.root if cfg else Path(__file__).resolve().parent.parent)
        self.cfg = cfg or AgentConfig.load(self.root)
        self.rules = RuleSource(self.cfg.workflow_root or None,
                                vendor_dir=self.root / "vendor")
        self.am = AssetManager(self.root, self.cfg.id_style)
        self.llm = LLMClient(self.cfg.llm_cfg)

    # ── 主入口 ──

    def handle(self, text: str, *, asset_type: str = "", generate: bool | None = None
               ) -> dict:
        """处理一句用户输入，返回结构化结果（供 CLI 或程序调用）。"""
        r, parsed = route(text, self.llm, asset_type)

        if r.operation == "query":
            return self._query(parsed.raw, asset_type or r.asset_type)

        if r.operation == "modify":
            return self._modify(r, parsed, generate)

        return self._create(r, parsed, generate)

    # ── 场景 360° 全景基准（§4.6）──

    def panorama(self, text: str, *, generate: bool | None = None) -> dict:
        """出场景的 **360° 全景空间基准**（§四·4.6）。

        工作流原话：「**全景定基准 → 六角度出分镜可用图**」——
        先出一张 360° 全景确定空间的完整布局，避免"只顾一面墙"导致后续多角度空间矛盾。

        两种用法：
          · 传 **`ENV_00X`** → 从已有场景**派生**一张全景基准卡（ID 加 `_PanoramaBase` 状态位）
          · 传 **场景描述** → 新建场景，并直接出它的全景基准
        """
        t = (text or "").strip()
        base = self.am.load(self.am.resolve_id(t)) if parse_id(t) else None

        if base is not None:
            card = AssetCard.from_dict(base.to_dict())
            card.id = f"{base.id}_PanoramaBase"
            card.version = "v001"
            card.parent_asset = base.id
            card.layout_variant = "panorama360"
            card.updated_at = now_str()
            card.source = f"{base.source} ｜ 360° 全景基准派生"
            notes = [f"从 {base.id} 派生 360° 全景基准（§4.6）"]
        else:
            r0, parsed = route(t, self.llm, "environment")
            aid = self.am.allocate_id("environment", note=f"360全景 {t[:30]}")
            card = scene_agent.build_card(parsed, aid, now_str())
            card.layout_variant = "panorama360"
            card, notes = scene_agent.complete(card, parsed, self.rules, self.llm)

        # 推荐参数（§4.6 表内为**真实参数**）—— 同时写进卡片 notes 与返回说明，
        # 否则 CLI 只显示卡片外的那几条，用户看不到该用哪些出图参数
        p = self.rules.panorama
        if p.get("params"):
            line = "§4.6 推荐参数（出图平台按此设置）：" + \
                " · ".join(f"{k}={v}" for k, v in p["params"].items())
            card.notes = (card.notes + " ｜ " if card.notes else "") + line
            notes.append(line)

        en, cn, neg = build_prompts(card, self.rules)
        rep = check_required(card, self.rules)
        result = self._maybe_generate(card, generate)
        notes.extend(self._gen_note(result))
        path = self.am.save(card)
        pr = self.am.write_prompt(card)
        md = self.am.write_metadata(card, result)
        notes.append("下一步：按 `INDEX-TEMPLATES.md` §4.1 出 S01–S06 六角度，"
                     "全部以本全景为空间参照")
        return {"operation": "panorama", "asset_id": card.id, "type": "environment",
                "version": card.version, "notes": notes, "card": card.to_dict(),
                "prompt_en": en, "prompt_cn": cn, "negative": neg,
                "images": result.image_paths, "consistency": rep,
                "files": {"card": str(path), "prompt": str(pr), "metadata": str(md)}}

    # ── 本机覆盖层的可见性 ──

    def _override_notes(self) -> list[str]:
        """把"本机覆盖生效了什么"写进返回说明。

        ⚠️ 覆盖层是**静默生效**的（不改变任何调用契约）—— 若不主动报告，
        用户会疑惑「prompt 为什么和上次不一样」、「我加的规则到底生效没」。
        这是本项目反复强调的同一件事：**静默的机制比坏掉的机制更难查**。
        """
        ov = self.rules.overrides
        if ov.is_empty() and not ov.unknown and not ov.problems:
            return []
        out: list[str] = []
        act = ov.active()
        if act:
            out.append("🧩 本机覆盖生效 %d 项（`prompts/overrides/`）：%s"
                       % (len(act), "、".join(o.rel for o in act)))
        if ov.unknown:
            out.append("⚠️ 覆盖层有 %d 个文件名不合约定、**未生效**：%s"
                       "（约定 `<scope>.<target>.md`，"
                       "scope=all|角色类名，target=negative|extra|layout）"
                       % (len(ov.unknown), "、".join(ov.unknown)))
        for p in ov.problems:
            out.append(f"⚠️ 覆盖层问题：{p}")
        return out

    # ── 产出核验（**图像层**）──

    def verify(self, asset_id: str) -> dict:
        """核验一张资产的**产出实物**（卡 / 提示词 / 图 / 索引表）。

        ⚠️⚠️ **本命令明确不判定「图与图是不是同一个人」。**
        那属于**图像语义比对**，没有视觉模型时无法可靠判定 —— 用像素/直方图硬凑出来的
        「一致/不一致」结论很可能是错的，而这一项偏偏最不能错（**脸崩了却报一致，
        比不检查更糟**）。故这里只核验**客观可验证**的部分，并把未核验项**显式列出**。

        核验项（都可通过/不通过）：
          · 资产卡：文件在、ID 与注册表一致、必填项过 Gate
          · 提示词：中英非空、负面词含**权重标记** `any text:1.8`（缺它文字屏蔽失效）
          · 图像：文件存在、非空、**PNG 尺寸 == 配置尺寸**、是 mock 还是真实出图
          · 场景：六角度是否齐全 + 索引表是否建了（§4.1「不建此表→空间必然漂移」）
        """
        card = self.am.load(self.am.resolve_id(asset_id))
        if card is None:
            return {"ok": False, "error": f"找不到资产 {asset_id!r}", "checks": []}

        checks: list[dict] = []

        def add(name: str, ok: bool | None, detail: str):
            checks.append({"name": name,
                           "ok": ok,
                           "detail": detail})

        # ① 资产卡
        add("资产卡存在", True, f"{card.id} · {card.type} · {card.version}")
        issued = self.am.registry.get("issued", {})
        add("ID 已登记", card.id in issued,
            "在 ID 注册表中" if card.id in issued else "⚠️ 未登记（§四 要求所有 ID 登记）")

        # ② 提示词
        add("英文提示词非空", bool(card.prompt_en.strip()),
            f"{len(card.prompt_en)} 字符")
        cn_left = [c for c in card.prompt_en if "\u4e00" <= c <= "\u9fff"]
        add("英文提示词无中文残留", not cn_left,
            "0 处" if not cn_left else f"{len(cn_left)} 处（{''.join(cn_left[:12])}…）")
        add("负面词含权重标记", "any text:1.8" in card.negative_prompt,
            "含 `any text:1.8`（缺它文字屏蔽失效，§1.6）"
            if "any text:1.8" in card.negative_prompt else "❌ 缺 `any text:1.8`")

        # ③ 图像
        img = (self.root / "output" / "images" / card.id / f"{card.version}.png")
        if img.exists():
            w, h = png_size(str(img))
            add("图像文件存在", True, f"{img.name} · {img.stat().st_size / 1024:.1f} KB")
            add("图像尺寸符合配置", (w, h) == (self.cfg.width, self.cfg.height),
                f"实际 {w}×{h}，配置 {self.cfg.width}×{self.cfg.height}")
            is_mock = self.cfg.provider == "mock"
            add("出图来源", None,
                "mock 占位图（版式示意，**不是成图**）" if is_mock
                else f"{self.cfg.provider} 真实出图")
        else:
            add("图像文件存在", False,
                "未找到（`--no-image` 或未出图）—— 提示词与卡仍可用")

        # ④ 场景专有：六角度 + 索引表
        if card.type == "environment":
            ad = self.root / "output" / "prompts" / f"{card.id}_angles" / "angles.json"
            if ad.exists():
                data = json.loads(ad.read_text(encoding="utf-8"))
                got = [i for i in data.get("items", []) if i.get("image")]
                add("六角度齐全", len(got) >= 6, f"{len(got)}/6 已出图")
                add("索引表已建", bool(data.get("index_table")),
                    "§4.1 要求必须建（不建则空间必然漂移）")
            else:
                add("六角度已生成", False,
                    "未生成 —— 跑 `python main.py angles " + card.id + "`")
            pano = (self.root / "assets" / "scenes" /
                    f"{card.id}_PanoramaBase" / "v001.json")
            add("360° 全景基准", pano.exists(),
                "已建" if pano.exists() else
                "未建（建议 `python main.py panorama " + card.id + "`）")

        # ⑤ §六 漂移检测（ID 是否都在总表里）—— 顺带核验本资产的交付物
        from . import drift
        known, _gap = drift.load_registry(self.root)
        pd = self.root / "output" / "prompts" / card.id
        unreg: list[str] = []
        for f in sorted(pd.glob("*.md")) if pd.is_dir() else []:
            unreg += drift.check_text(f.read_text(encoding="utf-8"), known).unregistered
        unreg = list(dict.fromkeys(unreg))
        add("§六 ID 漂移检测（交付物引用的 ID 都在总表里）", not unreg,
            "✅ 未发现未登记 ID" if not unreg
            else "引用了未登记 ID：" + "、".join(unreg[:6])
                 + "（`python main.py drift` 可全库检查）")

        # ⑥ 未核验项 —— **必须显式列出**，不能让人以为"verify 通过 = 一切都对"
        unchecked = [
            "**图与图是否同一角色/同一空间**（需视觉模型做语义比对，本命令不判定）",
            "图像内容是否符合描述（同上）",
            "文字是否真的没出现在图里（§1.6 要求**人工逐字**检查隐蔽位置："
            "背景招牌/书页/屏幕/衣物印字/包装/道具铭文）",
            "**ID 是否用在这里是对的**（`drift` 只验在不在总表）",
        ]
        ok = all(c["ok"] is not False for c in checks)
        return {"ok": ok, "asset_id": card.id, "type": card.type,
                "checks": checks, "unchecked": unchecked}

    # ── 场景六角度（`模板/INDEX-TEMPLATES.md` §4.1）──

    def angles(self, env_id: str, *, generate: bool | None = None,
               reference: str = "") -> dict:
        """出场景的 **S01–S06 六角度**，并产出 §4.1 要求的**场景资产库索引表**。

        ⚠️ 原文明确：「**不建此表 → 各角度独立从文字生成 → 空间必然漂移**」——
        故本方法把「索引表」当作**机制的一部分**产出，而不是可选文档。

        生成铁则（§4.1）：
          1. **必须先出 S01**（纯文字 prompt）；其 URL 存为 `_S01_url`
          2. **S02–S06 全部以 S01 为 reference_image**，追加 `same scene as reference`
          3. 每张只写该视角**实际可见**的物品
          4. 材质词/颜色词从场景圣经**复制**（同一 SceneDNA，不经改写）
        """
        card = self.am.load(self.am.resolve_id(env_id))
        if card is None:
            return {"operation": "angles", "ok": False,
                    "error": f"找不到场景 {env_id!r}（可用 `list --type environment` 查看）"}
        if card.type != "environment":
            return {"operation": "angles", "ok": False,
                    "error": f"{card.id} 是 {card.type}，六角度只对场景（environment）有效"}

        ang = self.rules.scene_angles
        sd = card.scene_dna
        # 全景基准（若已出过）作为空间参照一起带上
        pano_url = ""
        pano = self.root / "assets" / "scenes" / f"{card.id}_PanoramaBase" / "v001.json"
        if pano.exists():
            pano_url = f"output/images/{card.id}_PanoramaBase/v001.png"

        flag = self.cfg.generate if generate is None else generate
        prov = get_provider(self.cfg.provider, self.cfg.image_cfg) if flag else None

        urls: dict[str, str] = {}
        items: list[dict] = []
        ref = ""            # S01 出图后的路径，供 S02–S06 做 reference
        for a in ang["angles"]:
            no = a.get("no", "")
            en, cn = scene_agent.angle_prompts(sd, a, scene_name=card.name,
                                               ref_url=ref, pano_url=pano_url)
            neg = self.rules.negative_for("environment")
            for t in self.rules.scene_negative:
                if t and t not in neg:
                    neg = f"{neg}, {t}"
            img = ""
            if prov is not None:
                try:
                    out = self.root / "output" / "images" / f"{card.id}_angles" / f"{no}.png"
                    # ⭐ 铁则②的**真正落实**：S02–S06 把 S01 的**图**传给接口
                    #    （`reference=ref`），而不是只把路径写进提示词。
                    #    S01 自己渲染时 `ref` 仍为空串 → 自动不带参考图（铁则①：
                    #    S01 必须是**纯文字** prompt，带参考图就不是"基准"了）。
                    # ⚠️ S01 **永远**不带参考图（铁则①：它必须是纯文字基准），
                    #    故必须显式判 S01 —— 不能写成 `ref or reference`，
                    #    否则用户传了 `--reference` 时 S01 也会被挂图，"基准"就不成立了。
                    base = "" if no.upper() == "S01" else (ref or reference)
                    paths = prov.generate(prompt=en, negative_prompt=neg,
                                          width=self.cfg.width, height=self.cfg.height,
                                          out_path=str(out),
                                          reference=base or None)
                    img = str(paths[0]) if paths else ""
                except Exception as e:                               # noqa: BLE001
                    img = f"（出图失败：{str(e)[:60]}）"
            if img and not img.startswith("（"):
                urls[no] = f"{card.id}_{no}.png"
                if no.upper() == "S01":
                    ref = img          # 铁则 ①：S01 是后续所有角度的 reference
            items.append({"no": no, "shot": a.get("shot", ""), "cam": a.get("cam", ""),
                          "cover": a.get("cover", ""), "prompt_en": en,
                          "prompt_cn": cn, "negative": neg, "image": img})

        table = scene_agent.index_table(ang["angles"], urls)
        notes: list[str] = []
        if prov is None:
            notes.append("未出图（--no-image 或 config 关闭）—— 提示词与索引表已产出")
        elif not ref:
            if reference:
                notes.append(f"⚠️ S01 未出图 → 改用**用户提供**的参考图作为 "
                             f"S02–S06 的基图：{reference}（注意：这张不是本场景的纯文字基准，"
                             f"空间一致性由它决定）")
            else:
                notes.append("⚠️ S01 未成功出图 → S02–S06 **没有参考图可挂**"
                             "（铁则 ② 要求以 S01 为 reference_image）；"
                             "可用 `--reference <已有图>` 兜底")
        if ref:
            notes.append(f"✅ S01 已出图（{ref}）—— S02–S06 已把它的**图**传给接口，"
                         f"**不只是**把路径写进 prompt")
            if self.cfg.provider == "mock":
                notes.append("ℹ️ mock 不做真实图生图：它把参考图**混入配色并画左上白条**，"
                             "使「参考图是否真的传进来了」可用产物验证 "
                             "（同 prompt 有无参考图 → 两张图像素不同）。"
                             "真实图生图请用 openai / stability")
            else:
                notes.append(f"✅ **已真正挂图**（provider={self.cfg.provider}）："
                             f"openai 走 `/images/edits` · "
                             f"stability 走 `mode=image-to-image`")
        if not pano_url:
            notes.append("建议先出 `panorama`（§4.6 全景基准），六角度以它为空间参照")

        # 产出：索引表 + 全部角度提示词（一份人读的 md）
        d = self.root / "output" / "prompts" / f"{card.id}_angles"
        d.mkdir(parents=True, exist_ok=True)
        md = d / "index.md"
        body = [f"# {card.id} 场景多角度（{card.name}）", "",
                "> 依据 `02-服化道/模板/INDEX-TEMPLATES.md` §4.1。",
                "> **不建此表 → 各角度独立从文字生成 → 空间必然漂移。**", "",
                "## 场景资产库索引表", "", table, "",
                "## 生成铁则（§4.1 原文）", ""]
        body += [f"{i}. {r}" for i, r in enumerate(ang["rules"], 1)]
        body += ["", "## 分镜选图规则", "",
                 "| 分镜景别 | 优先 | 备选 |", "|---|---|---|"]
        body += [f"| {p['shot']} | {p['first']} | {p['alt']} |" for p in ang["picks"]]
        body += ["", "---", ""]
        for it in items:
            body += [f"## {it['no']} · {it['shot']}", "",
                     f"- 机位：{it['cam']}", f"- 可见范围：{it['cover']}",
                     f"- 出图：`{it['image'] or '（未出图）'}`", "",
                     "```text", it["prompt_en"], "```", "",
                     "```text", it["prompt_cn"], "```", ""]
        md.write_text("\n".join(body), encoding="utf-8")

        j = d / "angles.json"
        j.write_text(json.dumps({"asset_id": card.id, "index_table": table,
                                 "rules": ang["rules"], "picks": ang["picks"],
                                 "items": items}, ensure_ascii=False, indent=2),
                     encoding="utf-8")

        return {"operation": "angles", "ok": True, "asset_id": card.id,
                "count": len(items), "items": items, "index_table": table,
                "notes": notes, "files": {"index": str(md), "json": str(j)}}

    # ── 批量（蓝图 §十八）──

    def plan_batch(self, text: str, *, count: int = 0, asset_type: str = ""
                   ) -> tuple[str, list[dict]]:
        """规划一次批量：返回 `(asset_type, 展开后的 N 条请求)`。

        ⭐ 单独提出来，是为了让 **CLI 预览**与**实际执行**用**同一份规划** ——
        否则「预览里是主角/伙伴，实际生成的是拾荒者/商队护卫」这种不一致，
        用户根本没法判断哪边对（实测踩到：预览没传世界观，落到了通用池）。
        """
        if not asset_type:
            r0, p0 = route(text, self.llm, "")
            asset_type = r0.asset_type if r0.asset_type else "character"
            world = p0.world or ""
        else:
            _, p0 = route(text, self.llm, asset_type)
            world = p0.world or ""
        return asset_type, batch_mod.plan(text, count=count,
                                          asset_type=asset_type, world=world)

    def batch(self, text: str, *, count: int = 0, asset_type: str = "",
              generate: bool | None = None) -> dict:
        """一次生成多个资产 —— 蓝图 §十八「一次生成 10 个废土 NPC」。

        ⭐ **不做批量专用流水线**：把请求展开成 N 条自然语言请求，**各自走正常
        `handle()`** —— 于是每一项都自动获得同一套 Gate / 指纹 / 版本 / 落盘，
        不会出现「批量生成的与单个生成的不一样」这种最难查的偏差。
        """
        asset_type, items = self.plan_batch(text, count=count,
                                            asset_type=asset_type)
        results: list[dict] = []
        for it in items:
            try:
                res = self.handle(it["text"], asset_type=asset_type, generate=generate)
            except Exception as e:                                   # noqa: BLE001
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            card = res.get("card") or {}
            results.append({
                "index": it["index"], "label": it["label"], "text": it["text"],
                "ok": res.get("ok") is not False and "asset_id" in res,
                "asset_id": res.get("asset_id", ""),
                "name": card.get("name", ""),
                "version": res.get("version", ""),
                "status": card.get("id_status", ""),
                "consistency": (res.get("consistency").summary()
                                if res.get("consistency") else ""),
                "error": res.get("error", ""),
                "raw": res,
            })
        return {"operation": "batch", "asset_type": asset_type,
                "count": len(results), "items": results,
                "roster": batch_mod.roster(results)}

    # ── 创建 ──

    def _create(self, r, parsed, generate) -> dict:
        now = now_str()
        agent = AGENTS.get(r.asset_type, character_agent)
        # 表情/动作的 ID 模板含 `{owner}`/`{name}`（`EXP_<角色>_<表情名>` /
        # `POS_<3位>_<动作名>`）—— 由 agent 提供片段，否则会生成 `POS_001_` 这种
        # 带悬空分隔符的 ID。
        owner, name_hint = ("", "")
        if hasattr(agent, "id_hint"):
            owner, name_hint = agent.id_hint(parsed)
        aid = self.am.allocate_id(r.asset_type, note=parsed.raw[:40],
                                  owner=owner, name=name_hint)

        if hasattr(agent, "build_card"):
            card = agent.build_card(parsed, aid, now)
        else:
            card = AssetCard(id=aid, type=r.asset_type, name=parsed.name,
                             source=parsed.raw, created_at=now, updated_at=now,
                             world=parsed.world)

        card, notes = agent.complete(card, parsed, self.rules, self.llm)
        # ⭐ 锁定 / 可变集**在一处设置**，依权威推导：
        #    `locked`   ← §四·补 A「终身固定核心识别特征（100% 不可改动）」
        #    `editable` ← §四·补 B「剧情适配变量项（各状态卡之间可不同）」
        # ⚠️ 原先是 6 个 agent 各写一套，**每套都错**（抄注释举例 / 名字不在 §一 /
        #    语义反转 / 把中文空间要素当锁定项）—— 详见 `lock.default_locks()`。
        card.locked = card.locked or lock.default_locks(self.rules, card.type)
        card.editable = card.editable or lock.default_editable(self.rules, card.type)

        en, cn, neg = build_prompts(card, self.rules)
        notes.extend(name_suppressed_note(card))
        notes.extend(self._override_notes())

        rep = check_required(card, self.rules)
        rep.issues.extend(check_text_risk(en, neg).issues)

        result = self._maybe_generate(card, generate)
        notes.extend(self._gen_note(result))
        path = self.am.save(card)
        p = self.am.write_prompt(card)
        m = self.am.write_metadata(card, result)

        # §三 STEP 4 对**首次建立**同样适用 —— 模板首条即
        # `v1 · changed: ["初次生成"] · reason: "项目启动，建立 Character DNA"`，
        # 故创建时也追加一条（否则"每条版本都有记录"这个不变量从开始就不成立）。
        lock.append_entry(self.root, asset=card.id, version=card.version,
                          changed=["初次生成"], unchanged=[],
                          reason=f"创建：{parsed.raw}")

        return {
            "operation": "create", "asset_id": aid, "type": card.type,
            "version": card.version, "route": r.to_dict(), "parser": parsed.parser,
            "notes": notes, "card": card.to_dict(),
            "prompt_en": en, "prompt_cn": cn, "negative": neg,
            "images": result.image_paths, "consistency": rep,
            "files": {"card": str(path), "prompt": str(p), "metadata": str(m)},
        }

    # ── 修改 ──

    def _modify(self, r, parsed, generate) -> dict:
        # ⚠️ 带上 `asset_type` 限定 —— 否则「把她头发换成银白」在库里同时有
        #    场景时会改到场景上（见 `resolve_id` 的说明）
        aid = self.am.resolve_id(r.target_asset or parsed.target_asset,
                                 asset_type=r.asset_type)
        old = self.am.load(aid)
        if old is None:
            return {"operation": "modify", "ok": False,
                    "error": f"找不到资产 {aid!r}（可用 `list` 查看已有资产）"}

        new = AssetCard.from_dict(old.to_dict())
        new.version = self.am.next_version(aid)
        new.parent_asset = old.id
        new.updated_at = now_str()
        new.source = f"{old.source} ｜ 修改：{parsed.raw}"

        changes = self._apply_changes(new, parsed)

        # ── §三「修改执行四步（强制）」的 STEP 1 / STEP 2 ──
        #    STEP 1 解析指令 → LOCK/MODIFY 映射（§二 的自然语言 → 锁定表）
        #    STEP 2 冲突检测 → 改到锁定项就**列出来提示**（此前完全没有）
        directive = lock.parse_directive(parsed.raw, self.rules)
        lk = lock.detect_conflicts(old, parsed.change_fields or list(changes),
                                   self.rules, directive)
        # 锁定/可编辑终于有了落点（`AssetCard.locked` 字段此前定义了但无人写入）
        # ⚠️ `locked` 只写**指令明确声明的** LOCK 项（§二 的 `X=LOCK`）——
        #    **不能**写成"全部减 changed"，那会把"上次没改到的项"当锁定，
        #    于是用户下一次**明确要求**改它时被误报成"锁定项冲突"（实测踩到）。
        from_directive = [f"LOCK_{n}" for n, v in directive.items()
                          if v.upper() == "LOCK"]
        new.locked = sorted(set(from_directive) | set(old.locked or []) ) \
            if from_directive else list(old.locked or [])
        # 明确要求改的项 → 解除锁定
        new.locked = [x for x in new.locked
                      if x not in {f"LOCK_{n}" for n in lk.changed
                                   if directive.get(n, "").upper() == "MODIFY"}]
        new.editable = [f"LOCK_{n}" for n in lk.changed]

        # 改完重新出 Prompt（prompt 必须反映新设定）
        build_prompts(new, self.rules)

        # ⭐ 一致性 Gate：只改了用户要求的那部分？
        rep = check_modify_scope(old, new, parsed.change_fields or list(changes))
        rep.issues.extend(check_required(new, self.rules).issues)
        rep.issues.extend(check_text_risk(new.prompt_en, new.negative_prompt).issues)
        # §三 STEP 2 的冲突项并入 Gate 报告（**提示级**，不阻断 —— 原文说"提示用户"）
        for c in lk.conflicts:
            rep.add("warn", "LOCK_CONFLICT", f"锁定项冲突：{c}")

        result = self._maybe_generate(new, generate)
        self.am.save(new)
        p = self.am.write_prompt(new)
        m = self.am.write_metadata(new, result)

        # ⚠️ 修改路径原本**没有 notes 字段** —— 于是出图失败、本机覆盖生效
        #    这类"必须说出来"的信息全被丢掉（实测：给了错的 --reference，
        #    输出里一个字都没提）。补上。
        notes = self._gen_note(result) + self._override_notes()
        if self.cfg.reference_image and getattr(result, "ok", False):
            notes.append(f"🖼️ 本次挂了参考图做图生图：{self.cfg.reference_image}")
        # ⚠️ 防呆：改错对象时**说出来**。`resolve_id` 在该类型下无资产时会退回
        #    "最近创建的资产" —— 那可能是个场景/道具，于是一句"换发色"改到了不相干的东西上。
        if r.asset_type and old.type != r.asset_type:
            notes.append(f"⚠️ 本次改的是 {old.id}（**{old.type}**），"
                         f"但按措辞判定应为 `{r.asset_type}` —— "
                         f"库里似乎没有该类型的资产，请确认改对了对象")

        # ── §三 STEP 4「记录变更」：追加 CHANGELOG（**强制步骤**）──
        #    模板 §项目管理 明文：「changed / unchanged 必须完整，不得省略」，
        #    故即使为空也显式写出 `[]`（本模块的 `append_entry` 保证这点）。
        cl = lock.append_entry(self.root, asset=new.id, version=new.version,
                               changed=lk.changed, unchanged=lk.unchanged,
                               reason=parsed.raw)
        notes.append(f"📝 变更记录已追加（§三 STEP 4）：`{lock.CHANGELOG_REL}` ｜ "
                     f"changed={lk.changed or '[]'} ｜ unchanged {len(lk.unchanged)} 项")
        # §三 STEP 2 的冲突**必须说出来**（原文：「列出…并提示用户」）
        if lk.conflicts:
            notes.append(f"⚠️ **锁定项冲突 {len(lk.conflicts)} 处**（§三 STEP 2）—— "
                         f"本次变更会改动卡片上已锁定的项；"
                         f"若确实要改，请明说「只改 X」或先解除锁定")
        notes.extend(lk.notes)

        return {
            "operation": "modify", "ok": True, "asset_id": aid,
            "notes": notes,
            "from_version": old.version, "version": new.version,
            "changes": changes, "route": r.to_dict(),
            "diff": self.am.diff_versions(aid, old.version, new.version),
            "card": new.to_dict(), "prompt_en": new.prompt_en,
            "prompt_cn": new.prompt_cn, "negative": new.negative_prompt,
            "images": result.image_paths, "consistency": rep,
            "lock": {"directive": lk.directive, "changed": lk.changed,
                     "unchanged": lk.unchanged, "conflicts": lk.conflicts,
                     "changelog": str(cl)},
            "files": {"card": str(self.am.card_path(aid, new.version)),
                      "prompt": str(p), "metadata": str(m)},
        }

    def _apply_changes(self, card: AssetCard, parsed) -> dict:
        """按 `parsed.change_fields` 只改对应字段。"""
        vd, sv = card.visual_dna, card.stage_variables
        done: dict = {}
        text = parsed.raw

        # 从原文里抽新值（「换成银色」→ 银）
        new_colors = [c for c in parsed.color_hints] or []
        new_hairs = [h for h in parsed.hair_hints] or []

        for f in parsed.change_fields:
            if f == "hair_color" and new_colors:
                _set_pair(vd, "hair_color", new_colors[0])
                done["hair_color"] = vd.hair_color
            elif f in ("hair", "hair_style"):
                if new_hairs:
                    for h in new_hairs:
                        if h.endswith("发") or h in ("长发", "短发", "中长发", "马尾"):
                            _set_pair(vd, "hair_length", h)
                        else:
                            _set_pair(vd, "hair_style", h)
                    done["hair"] = f"{vd.hair_length}/{vd.hair_style}"
                if new_colors:
                    _set_pair(vd, "hair_color", new_colors[0])
                    done["hair_color"] = vd.hair_color
            elif f == "eye_color" and new_colors:
                _set_pair(vd, "eye_color", new_colors[0])
                done["eye_color"] = vd.eye_color
            elif f == "clothing":
                if "皮" in text:
                    _set_pair(vd, "material", "皮革")
                    done["material"] = vd.material
                if new_colors:
                    _set_pair(vd, "primary_color", new_colors[0] + "系")
                    done["primary_color"] = vd.primary_color
            elif f == "color" and new_colors:
                _set_pair(vd, "primary_color", new_colors[0])
                done["primary_color"] = vd.primary_color
            elif f in ("cybernetic_arm", "cybernetic_leg", "cybernetic_eye"):
                part = {"cybernetic_arm": "机械臂", "cybernetic_leg": "机械腿",
                        "cybernetic_eye": "机械义眼"}[f]
                side = "左" if "左" in text else ("右" if "右" in text else "")
                spec = f"机械{side}{part.replace('机械', '')}" if side else part
                spec_en = {"机械左臂": "cybernetic left arm",
                           "机械右臂": "cybernetic right arm",
                           "机械左腿": "cybernetic left leg",
                           "机械右腿": "cybernetic right leg",
                           "机械臂": "cybernetic arm", "机械腿": "cybernetic leg",
                           "机械义眼": "cybernetic eye"}.get(spec, spec)
                vd.signature_accessory = "；".join(
                    dict.fromkeys([x for x in [vd.signature_accessory, spec] if x]))
                vd.signature_accessory_en = ", ".join(
                    dict.fromkeys([x for x in [vd.signature_accessory_en, spec_en] if x]))
                sv.core_accessories = vd.signature_accessory
                sv.core_accessories_en = vd.signature_accessory_en
                if spec not in vd.signature_points:
                    vd.signature_points.append(spec)
                    vd.signature_points_en.append(spec_en)
                done[f] = spec
            elif f == "age":
                import re
                m = re.search(r"(\d{1,3})\s*岁", text)
                if m:
                    card.age = int(m.group(1))
                    sv.aging_marks = f"约 {card.age} 岁面貌"
                    done["age"] = card.age
            elif f == "body":
                for kw, v in (("更瘦", "slimmer"), ("更强壮", "more muscular"),
                              ("更高", "taller"), ("更矮", "shorter")):
                    if kw in text:
                        vd.body_type = v
                        vd.body_type_en = v
                        done["body_type"] = v
        if not done:
            done["_note"] = f"未识别出可改字段（意图字段={parsed.change_fields}）"
        return done

    # ── 查询 ──

    def _query(self, text: str, asset_type: str) -> dict:
        keyword = ""
        for k in ("机械", "废土", "赛博", "银发", "长发", "废墟", "霓虹", "指挥中心"):
            if k in text:
                keyword = k
                break
        # 「列出所有武器 / 所有场景 / 所有表情集」这类**按对象名查**。
        # ⚠️ 原版只认武器词并**无条件覆盖**路由结果 → 「查看角色的武器」会变成只查道具。
        #    现在按对象词推断，且**只在能推断出类型时才覆盖**。
        hint = _type_from_object(text)
        if hint:
            asset_type = hint
        cards = self.am.list_assets(asset_type=asset_type, keyword=keyword)
        return {"operation": "query", "asset_type": asset_type, "keyword": keyword,
                "count": len(cards),
                "items": [{"id": c.id, "name": c.name, "type": c.type,
                           "world": c.world, "version": c.version,
                           "status": c.id_status} for c in cards]}

    # ── 出图 ──

    def _maybe_generate(self, card: AssetCard, generate: bool | None):
        from .schema import GenerationResult
        flag = self.cfg.generate if generate is None else generate
        if not flag:
            return GenerationResult(asset_id=card.id, version=card.version,
                                    provider="(skipped)", model="", ok=True)
        t0 = time.time()
        # ⚠️ **先归一版本号**，再拿它拼路径 —— `_maybe_generate` 跑在 `save()` 之前，
        #    若此处不归一，图会存成 `v1.png` 而卡是 `v001.json`（实测踩到，
        #    后果是 `--reference` 指向旧图时**永远指空**）。所有生成路径都汇到这里，
        #    故这是唯一收口点。
        from .asset_manager import normalize_version
        card.version = normalize_version(card.version)
        prov = get_provider(self.cfg.provider, self.cfg.image_cfg)
        out_dir = self.root / "output" / "images" / card.id / f"{card.version}.png"
        try:
            paths = prov.generate(prompt=card.prompt_en, negative_prompt=card.negative_prompt,
                                  width=self.cfg.width, height=self.cfg.height,
                                  out_path=str(out_dir),
                                  reference=self.cfg.reference_image or None)
            final = self.am.place_images(card, paths)
            return GenerationResult(
                asset_id=card.id, version=card.version, provider=prov.name,
                model=getattr(prov, "model", prov.name), image_paths=final,
                width=self.cfg.width, height=self.cfg.height, ok=True,
                duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return GenerationResult(
                asset_id=card.id, version=card.version, provider=prov.name,
                model=getattr(prov, "model", prov.name), ok=False, error=str(e),
                duration_ms=int((time.time() - t0) * 1000))

    # ── 出图失败的可见性 ──

    @staticmethod
    def _gen_note(result) -> list[str]:
        """出图失败必须**说出原因**。

        ⚠️ 实测踩到：`--reference` 给了不存在的路径 → 资产卡照常创建、图没有、
        输出里**一个字都没提**。用户只会以为"图还没好"，而真相是
        "参考图路径错了"，两者处理方式完全不同。这是本项目最怕的**静默失败**。
        """
        if getattr(result, "ok", True):
            return []
        return [f"❌ **出图失败**（provider={getattr(result, 'provider', '?')}）："
                f"{getattr(result, 'error', '（无错误信息）')}"]

    # ── 自检 ──

    def doctor(self) -> dict:
        """环境自检：规则源 / LLM / Provider / 目录。"""
        from .image_provider import list_providers
        rep = self.rules.verify_snapshot()
        return {
            "root": str(self.root),
            "rules": self.rules.summary(),
            "snapshot": {"ok": rep.ok, "detail": rep.detail,
                         "missing": rep.missing, "changed": rep.changed},
            "llm": self.llm.status(),
            "providers": [{"name": p.name, "available": p.available, "reason": p.reason}
                          for p in list_providers(self.cfg.image_cfg)],
            "active_provider": self.cfg.provider,
            "asset_count": len(self.am.list_assets()),
            "text_risk_checklist": text_risk_checklist(),
        }
