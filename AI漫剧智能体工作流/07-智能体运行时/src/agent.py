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

from . import (character_agent, costume_agent, expression_agent, pose_agent,
               prop_agent, prompt_engine, scene_agent)
from .asset_manager import AssetManager, now_str
from .consistency import (ConsistencyReport, check_modify_scope, check_required,
                          check_text_risk, full_check, text_risk_checklist)
from .image_provider import get_provider
from .llm_client import LLMClient
from .prompt_engine import build_prompts
from .router import route
from .rule_source import RuleSource
from .schema import AssetCard

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
        en, cn, neg = build_prompts(card, self.rules)

        rep = check_required(card, self.rules)
        rep.issues.extend(check_text_risk(en, neg).issues)

        result = self._maybe_generate(card, generate)
        path = self.am.save(card)
        p = self.am.write_prompt(card)
        m = self.am.write_metadata(card, result)

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
        aid = self.am.resolve_id(r.target_asset or parsed.target_asset)
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

        # 改完重新出 Prompt（prompt 必须反映新设定）
        build_prompts(new, self.rules)

        # ⭐ 一致性 Gate：只改了用户要求的那部分？
        rep = check_modify_scope(old, new, parsed.change_fields or list(changes))
        rep.issues.extend(check_required(new, self.rules).issues)
        rep.issues.extend(check_text_risk(new.prompt_en, new.negative_prompt).issues)

        result = self._maybe_generate(new, generate)
        self.am.save(new)
        p = self.am.write_prompt(new)
        m = self.am.write_metadata(new, result)

        return {
            "operation": "modify", "ok": True, "asset_id": aid,
            "from_version": old.version, "version": new.version,
            "changes": changes, "route": r.to_dict(),
            "diff": self.am.diff_versions(aid, old.version, new.version),
            "card": new.to_dict(), "prompt_en": new.prompt_en,
            "prompt_cn": new.prompt_cn, "negative": new.negative_prompt,
            "images": result.image_paths, "consistency": rep,
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
        prov = get_provider(self.cfg.provider, self.cfg.image_cfg)
        out_dir = self.root / "output" / "images" / card.id / f"{card.version}.png"
        try:
            paths = prov.generate(prompt=card.prompt_en, negative_prompt=card.negative_prompt,
                                  width=self.cfg.width, height=self.cfg.height,
                                  out_path=str(out_dir))
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
