# -*- coding: utf-8 -*-
"""Costume Agent —— 服装**独立成资产**（蓝图 §五）。

`TURNAROUND-STANDARD.md` §二 明文：**服装必须独立成资产，不得依附人物图。**
好处（蓝图 §五）：服装可绑定角色，一句「给 CHAR-001 换成 COSTUME-002」即可换装。

必填字段 25 项来自工作流 §2.1：
    时代·身份·阶层·用途·版型·剪裁·领型·袖型·肩部·腰部·下摆·扣件·缝线·
    刺绣·纹样·层次·面料·厚度·垂坠·磨损·使用痕迹·主色·辅色·配件·穿戴逻辑
"""

from __future__ import annotations

from .schema import AssetCard, StageVariables, VisualDNA

# 服装类型 → 结构化预设（按工作流 9 层穿戴逻辑组织）
COSTUME_PRESETS: dict[str, dict] = {
    "战术": {"silhouette": "多层机能廓形，上宽下收",
             "layers": "内层紧身衣 + 中层抓绒 + 外层防撕裂风衣 + 腰部战术背心",
             "material": "战术尼龙", "primary": "军绿 + 泥土棕",
             "accessory": "模块化弹匣袋、肩部织带、护膝织带",
             "wear": "肘部与下摆磨损、膝部加固补片起毛"},
    "礼服": {"silhouette": "修身收腰，裙摆或下摆自然垂坠",
             "layers": "内层衬裙 + 主体礼服 + 外披肩 + 腰间束带",
             "material": "亚麻", "primary": "月白 + 黛青",
             "accessory": "盘扣、织锦腰带、玉佩",
             "wear": "布料有自然垂坠褶皱，接缝平整"},
    "制服": {"silhouette": "硬挺直线廓形，肩线明确",
             "layers": "内层衬衫 + 中层马甲 + 外制服外套 + 制式腰带",
             "material": "羊毛", "primary": "藏青 + 银",
             "accessory": "领章、肩章、制式皮带、袖扣",
             "wear": "袖口轻微起光，前襟挺括"},
    "甲胄": {"silhouette": "外置硬质结构，肩部外扩",
             "layers": "内层软甲 + 中层锁甲 + 外层板甲 + 披风",
             "material": "磨砂钢", "primary": "旧金 + 深棕",
             "accessory": "肩甲、臂甲、护心镜、皮革系带",
             "wear": "甲片有凹痕与划痕、系带磨白"},
}
DEFAULT_COSTUME = {
    "silhouette": "功能性与辨识度兼顾的廓形",
    "layers": "内层 + 中间层 + 外层 + 腰带配件",
    "material": "棉", "primary": "深灰黑 + 暗红",
    "accessory": "一件与身份匹配的标志性配件",
    "wear": "均匀轻微使用痕迹",
}


def _set_if_empty(dc, fld: str, val) -> bool:
    cur = getattr(dc, fld, None)
    if cur in ("", None, [], ()):
        setattr(dc, fld, val)
        return True
    return False


def _pick(text: str) -> dict:
    for k, v in COSTUME_PRESETS.items():
        if k in text:
            return v
    return DEFAULT_COSTUME


def complete(card: AssetCard, parsed, rules, llm=None) -> tuple[AssetCard, list[str]]:
    notes: list[str] = []
    vd: VisualDNA = card.visual_dna
    sv: StageVariables = card.stage_variables
    preset = _pick(parsed.raw)

    _set_if_empty(vd, "silhouette", preset["silhouette"])
    _set_if_empty(vd, "layers", preset["layers"])
    _set_if_empty(vd, "material", preset["material"])
    _set_if_empty(vd, "primary_color", preset["primary"])
    _set_if_empty(vd, "signature_accessory", preset["accessory"])
    _set_if_empty(vd, "surface_texture", preset["wear"])
    _set_if_empty(sv, "full_outfit", preset["layers"])
    _set_if_empty(vd, "structure", preset["layers"])
    _set_if_empty(vd, "wear", preset["wear"])

    if parsed.material_hints:
        vd.material = "、".join(parsed.material_hints)
        notes.append(f"⚠️ 采用用户指定面料：{vd.material}")

    _set_if_empty(vd, "signature_points",
                  [preset["silhouette"].split("，")[0], preset["accessory"].split("、")[0]])

    if not card.locked:
        card.locked = ["CUT", "LAYER_ORDER"]
    if not card.editable:
        card.editable = ["COLOR", "WASH"]

    need = rules.costume_fields
    notes.append(f"服装必填字段 {len(need)} 项：" + "、".join(need[:8]) + "…")
    notes.append("穿戴逻辑（工作流 9 层）：内层 → 中层 → 外层 → 护具 → 腰部 → "
                 "腿部 → 鞋靴 → 饰品 → 特殊装备")
    return card, notes


def build_card(parsed, asset_id: str, now: str) -> AssetCard:
    return AssetCard(
        id=asset_id, type="costume",
        name=parsed.name or (parsed.raw[:16] if parsed.raw else "costume"),
        source=parsed.raw, created_at=now, updated_at=now, world=parsed.world,
    )
