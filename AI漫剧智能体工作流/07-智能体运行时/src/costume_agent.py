# -*- coding: utf-8 -*-
"""Costume Agent —— 服装**独立成资产**（蓝图 §五）。

`TURNAROUND-STANDARD.md` §二 明文：**服装必须独立成资产，不得依附人物图。**
好处（蓝图 §五）：服装可绑定角色，一句「给 CHAR-001 换成 COSTUME-002」即可换装。

必填字段 25 项来自工作流 §2.1：
    时代·身份·阶层·用途·版型·剪裁·领型·袖型·肩部·腰部·下摆·扣件·缝线·
    刺绣·纹样·层次·面料·厚度·垂坠·磨损·使用痕迹·主色·辅色·配件·穿戴逻辑
"""

from __future__ import annotations

from .nl_parser import short_name
from .prompt_engine import tr        # 复用词表，保证中英字段成对
from .schema import AssetCard, StageVariables, VisualDNA

# 服装类型 → 结构化预设（按工作流 9 层穿戴逻辑组织）
# ⚠️ 每个字段**中英成对**：只给中文会让英文 prompt 夹中文（实测踩到）。
COSTUME_PRESETS: dict[str, dict] = {
    "战术": {"silhouette": "多层机能廓形，上宽下收",
             "silhouette_en": "multi-layer technical silhouette, wide upper and tapered lower",
             "layers": "内层紧身衣 + 中层抓绒 + 外层防撕裂风衣 + 腰部战术背心",
             "layers_en": "base tight layer + fleece mid layer + ripstop outer coat + waist tactical vest",
             "material": "战术尼龙", "material_en": "tactical nylon",
             "primary": "军绿 + 泥土棕", "primary_en": "military green and earth brown",
             "accessory": "模块化弹匣袋、肩部织带、护膝织带",
             "accessory_en": "modular magazine pouches, shoulder webbing, knee webbing",
             "wear": "肘部与下摆磨损、膝部加固补片起毛",
             "wear_en": "worn elbows and hem, pilled knee reinforcement patches"},
    "礼服": {"silhouette": "修身收腰，裙摆或下摆自然垂坠",
             "silhouette_en": "fitted waist, skirt or hem falling naturally",
             "layers": "内层衬裙 + 主体礼服 + 外披肩 + 腰间束带",
             "layers_en": "underskirt + main gown + outer shawl + waist sash",
             "material": "亚麻", "material_en": "linen",
             "primary": "月白 + 黛青", "primary_en": "moon white and dark cyan",
             "accessory": "盘扣、织锦腰带、玉佩",
             "accessory_en": "frog buttons, brocade sash, jade pendant",
             "wear": "布料有自然垂坠褶皱，接缝平整",
             "wear_en": "natural drape creases, flat seams"},
    "制服": {"silhouette": "硬挺直线廓形，肩线明确",
             "silhouette_en": "stiff straight silhouette, defined shoulder line",
             "layers": "内层衬衫 + 中层马甲 + 外制服外套 + 制式腰带",
             "layers_en": "shirt + waistcoat + uniform coat + service belt",
             "material": "羊毛", "material_en": "wool",
             "primary": "藏青 + 银", "primary_en": "navy and silver",
             "accessory": "领章、肩章、制式皮带、袖扣",
             "accessory_en": "collar patches, epaulettes, service belt, cufflinks",
             "wear": "袖口轻微起光，前襟挺括",
             "wear_en": "slight shine on cuffs, crisp placket"},
    "甲胄": {"silhouette": "外置硬质结构，肩部外扩",
             "silhouette_en": "external hard structure, flared shoulders",
             "layers": "内层软甲 + 中层锁甲 + 外层板甲 + 披风",
             "layers_en": "padded base + chainmail + plate armour + cloak",
             "material": "磨砂钢", "material_en": "brushed steel",
             "primary": "旧金 + 深棕", "primary_en": "old gold and dark brown",
             "accessory": "肩甲、臂甲、护心镜、皮革系带",
             "accessory_en": "pauldrons, vambraces, breastplate, leather lacing",
             "wear": "甲片有凹痕与划痕、系带磨白",
             "wear_en": "dented and scratched plates, whitened lacing"},
}
DEFAULT_COSTUME = {
    "silhouette": "功能性与辨识度兼顾的廓形",
    "silhouette_en": "functional, readable silhouette",
    "layers": "内层 + 中间层 + 外层 + 腰带配件",
    "layers_en": "base layer + mid layer + outer layer + belt accessories",
    "material": "棉", "material_en": "cotton",
    "primary": "深灰黑 + 暗红", "primary_en": "dark grey-black and dark red",
    "accessory": "一件与身份匹配的标志性配件",
    "accessory_en": "one signature accessory matching the station",
    "wear": "均匀轻微使用痕迹", "wear_en": "even, light wear",
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

    # 中文进 prompt_cn，英文伴生进 prompt_en（**成对写入**，缺英文会夹中文）
    for fld, key in (("silhouette", "silhouette"), ("layers", "layers"),
                     ("material", "material"), ("primary_color", "primary"),
                     ("signature_accessory", "accessory"),
                     ("surface_texture", "wear"), ("structure", "layers"),
                     ("wear", "wear")):
        _set_if_empty(vd, fld, preset[key])
        _set_if_empty(vd, fld + "_en", preset.get(key + "_en", ""))
    _set_if_empty(vd, "craft", "常规缝制")
    _set_if_empty(vd, "craft_en", "conventional stitching")
    _set_if_empty(sv, "full_outfit", preset["layers"])
    _set_if_empty(sv, "full_outfit_en", preset["layers_en"])

    if parsed.material_hints:
        vd.material = "、".join(parsed.material_hints)
        vd.material_en = ", ".join(tr(m) for m in parsed.material_hints)
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
        # ⚠️ 用 `short_name` 而不是 `raw[:16]` —— 后者会把**整句用户输入**
        #    当资产名（实测：名字成了「给女佣兵设计一套破损军用风衣」，还整串进了英文 prompt）。
        name=parsed.name or short_name(parsed.raw) or "costume",
        source=parsed.raw, created_at=now, updated_at=now, world=parsed.world,
    )
