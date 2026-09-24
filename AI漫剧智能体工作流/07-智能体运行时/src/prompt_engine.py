# -*- coding: utf-8 -*-
"""Prompt Engine —— 结构化资产卡 → 中英双语 MASTER PROMPT。

═══════════════════════════════════════════════════════════════════
职责边界（蓝图 §七）
═══════════════════════════════════════════════════════════════════
    「Prompt Agent **不负责创造人物本身**，只负责把结构化数据转换成
      Image Prompt / Negative Prompt / Layout Prompt / Consistency Prompt。」

⚠️ 本模块**不硬编码任何规则** —— 负面词、三视图标准段、文字屏蔽、质量参数
   全部从 `RuleSource`（工作流的权威文件）实时读取。
   这是工作流质量守则 §2「单一权威来源」在代码层的落实。

输出结构（依用户素材 SYSTEM_PROMPT.md §17）
    Subject · Appearance · Body · Clothing · Materials · Equipment
    Color · Pose · Layout · Three-view · Lighting · Background
    Rendering · Consistency      (+ Negative)
"""

from __future__ import annotations

import re

from .schema import AssetCard

# 中文视觉词 → 英文（保证 prompt 真的可用，而非中英混排）
ZH2EN: dict[str, str] = {
    "female": "female", "male": "male",
    "wasteland": "post-apocalyptic wasteland", "cyberpunk": "cyberpunk",
    "scifi": "science fiction futuristic", "fantasy": "high fantasy",
    "dark_fantasy": "dark fantasy gothic", "ancient": "ancient oriental / wuxia",
    "western_fantasy": "western medieval fantasy", "steampunk": "steampunk",
    "modern": "modern urban contemporary", "military": "military tactical",
    "mecha": "hardcore mecha",
    "棉": "cotton", "亚麻": "linen", "牛仔": "denim", "皮革": "leather",
    "人造皮革": "faux leather", "防水织物": "waterproof fabric",
    "战术尼龙": "tactical nylon", "凯夫拉纤维": "Kevlar fiber",
    "碳纤维": "carbon fiber", "钛合金": "titanium alloy",
    "铝合金": "aluminium alloy", "磨砂钢": "brushed steel",
    "镀铬金属": "chrome-plated metal", "黄铜": "brass", "铜": "copper",
    "陶瓷": "ceramic", "玻璃": "glass", "亚克力": "acrylic",
    "橡胶": "rubber", "硅胶": "silicone", "毛皮": "fur", "羽毛": "feather",
    "木材": "wood", "石材": "stone", "魔法晶体": "magic crystal",
    "生物组织": "biological tissue",
    "风衣": "trench coat", "外套": "outer jacket", "制服": "uniform",
    "战衣": "combat suit", "盔甲": "armor", "斗篷": "cape", "军装": "military fatigues",
    "长袍": "long robe", "衬衫": "shirt", "皮夹克": "leather jacket",
    "军靴": "combat boots", "手套": "gloves", "腰带": "utility belt",
    "护甲": "protective armor", "肩甲": "pauldron", "背包": "tactical backpack",
    "面具": "face mask", "头盔": "helmet", "护目镜": "goggles",
    "机械左臂": "cybernetic left arm", "机械右臂": "cybernetic right arm",
    "机械手臂": "cybernetic arm", "机械腿": "cybernetic leg",
    "机械右腿": "cybernetic right leg", "机械左腿": "cybernetic left leg",
    "机械义眼": "cybernetic eye", "义眼": "artificial eye", "义肢": "prosthetic limb",
    "枪套": "holster", "匕首": "dagger", "佩剑": "sword", "手杖": "cane",
    "长发": "long hair", "短发": "short hair", "中长发": "medium-length hair",
    "及腰": "waist-length hair", "马尾": "ponytail", "双马尾": "twin tails",
    "编发": "braided hair", "大背头": "slicked-back hair", "寸头": "buzz cut",
    "卷发": "curly hair", "直发": "straight hair", "刘海": "bangs",
    "狼尾": "wolf cut", "波波头": "bob cut", "背头": "combed-back hair",
    "碎发": "choppy layered hair", "乱发": "messy hair", "束发": "tied-up hair",
    "丸子头": "top bun",
    "黑": "black", "白": "white", "灰": "gray", "银": "silver", "金": "gold",
    "红": "red", "暗红": "dark red", "酒红": "wine red", "橙": "orange",
    "黄": "yellow", "绿": "green", "青": "cyan", "蓝": "blue", "紫": "purple",
    "粉": "pink", "棕": "brown", "米": "beige", "藏青": "navy",
}

WORLD_RENDER = {k: f"photorealistic {v} cinematic concept art" for k, v in {
    "wasteland": "post-apocalyptic", "cyberpunk": "cyberpunk",
    "scifi": "science-fiction", "fantasy": "high-fantasy",
    "dark_fantasy": "dark-fantasy", "ancient": "ancient-oriental",
    "western_fantasy": "western-fantasy", "steampunk": "steampunk",
    "modern": "modern-urban", "military": "military", "mecha": "hardcore-mecha",
}.items()}

DEFAULT_RENDER = ("photorealistic ultra-detailed cinematic character concept art, "
                  "professional game character design sheet")

# 职业 → 英文（`nl_parser` 抽出的中文职业词，进 prompt 前必须译）
OCCUPATION_EN = {
    "佣兵": "mercenary", "雇佣兵": "mercenary", "杀手": "assassin", "刺客": "assassin",
    "医生": "doctor", "护士": "nurse", "侦探": "detective", "警探": "detective",
    "警察": "police officer", "工程师": "engineer", "科学家": "scientist",
    "教授": "professor", "博士": "scholar", "士兵": "soldier", "军人": "soldier",
    "将军": "general", "元帅": "marshal", "黑客": "hacker", "机修师": "mechanic",
    "拾荒者": "scavenger", "猎人": "hunter", "商人": "merchant",
    "老板娘": "bar owner", "船长": "captain", "飞行员": "pilot", "骑士": "knight",
    "法师": "mage", "剑客": "swordsman", "武僧": "monk", "皇帝": "emperor",
    "公爵": "duke", "公主": "princess", "王子": "prince", "教主": "cult leader",
    "记者": "journalist", "教师": "teacher", "学生": "student",
    "程序员": "programmer", "设计师": "designer", "司机": "driver",
    "厨师": "chef", "农民": "farmer", "女佣兵": "female mercenary",
}


def tr(text: str) -> str:
    """中英混排片段里能翻的词翻成英文；翻不了的原样保留（不丢信息）。"""
    if not text:
        return ""
    out = text
    for zh in sorted(ZH2EN, key=len, reverse=True):
        if zh in out and all(ord(c) > 127 for c in zh):
            out = out.replace(zh, ZH2EN[zh])
    return out


def _join(parts, sep: str = ", ") -> str:
    seen, out = set(), []
    for p in parts:
        p = (p or "").strip(" ,;，、")
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return sep.join(out)


def pick(en: str, cn: str) -> str:
    """**二选一**：有英文伴生字段就用它，否则才把中文兜底翻译。

    ⚠️ 关键：绝不能「英文 + 中文都拼进去」——
    那样 prompt 里会同时出现 `dark brown` 和 `深brown`，
    模型会收到互相冗余的噪声（实测就是这个 bug）。
    """
    e = (en or "").strip()
    if e:
        return e
    return tr((cn or "").strip())


def pick_list(en_items, cn_items) -> list[str]:
    """列表版 `pick`：按位取英文；英文缺位才用对应中文兜底。"""
    ens = list(en_items or [])
    cns = list(cn_items or [])
    n = max(len(ens), len(cns))
    out = []
    for i in range(n):
        e = (ens[i] if i < len(ens) else "") or ""
        c = (cns[i] if i < len(cns) else "") or ""
        v = pick(e, c)
        if v:
            out.append(v)
    return out


def _en(values) -> str:
    """兼容入口：把若干「已是英文」的片段拼起来（不做翻译）。"""
    return _join([v for v in values if v])


# ─────────────────────────────────────────────────────────────
# 版式段（三视图硬标准来自工作流，此处只做「组合」）
# ─────────────────────────────────────────────────────────────

def _fill_scene_seg(seg: str, sd) -> str:
    """把场景英文段里的 `[占位符]` 换成实际场景 DNA 值（英文优先）。

    工作流 §4.4 给的是**带占位符的骨架**：
        `Cinematic environment, [建筑类型], [空间尺度], [材料], [光线方向与性质], [氛围], …`
    直接用会在英文 prompt 里留 5 个中文占位符 —— 必须替换掉。
    """
    pairs = [("[建筑类型]", sd.building_en or sd.building),
             ("[空间尺度]", sd.spatial_scale_en or sd.spatial_scale),
             ("[材料]", sd.materials_en or sd.materials),
             ("[光线方向与性质]", sd.light_source_en or sd.light_source),
             ("[氛围]", sd.atmosphere_en or sd.atmosphere),
             ("[建筑风格]", sd.architectural_style_en or sd.architectural_style)]
    for k, v in pairs:
        if v:
            seg = seg.replace(k, v)
    # 仍存的占位符（字段未补全）→ 去掉方括号，避免进 prompt 干扰模型
    return re.sub(r"\[[^\]]*\]", "", seg).replace(", ,", ",").strip()


def _scene_keywords(sd) -> str:
    """把 SceneDNA 压成一句「[场景描述]」——供全景模板的占位符替换。"""
    return _join([pick(sd.building_en, sd.building),
                  pick(sd.materials_en, sd.materials),
                  pick(sd.atmosphere_en, sd.atmosphere)])


def _layout_block(rules, card) -> tuple[str, str]:
    """返回 (版式段, 一致性段)；先取工作流权威段，再套用**本机覆盖**。

    ⚠️ 入参从 `asset_type` 改为 **`card`**（2026-09-24）：场景版式需要 `scene_dna`
    才能填掉工作流骨架里的占位符；表情/动作版式需要 `sheet_dna` 的网格与表项。

    ⭐ 本机覆盖（`prompts/overrides/<scope>.layout.md`）**只替换 LAYOUT 段**，
    **一致性段仍取工作流** —— 不能让一个本机文件悄悄抹掉权威的一致性约束
    （那正是「图会漂移」的开始）。
    """
    layout, cons = _layout_workflow(rules, card)
    ov = _ovr(rules)
    if ov is not None:
        seg = ov.layout(card.type)
        if seg:
            return f"LAYOUT: {seg}", cons
    return layout, cons


def _ovr(rules):
    """取 `rules` 上挂的本机覆盖层（没有则 None）。

    统一从这里取，是为了**所有调用点自动生效** —— 若改成"由调用方传参"，
    漏传一处就会静默不生效（本项目最怕的失败形态）。
    """
    ov = getattr(rules, "overrides", None)
    return ov if (ov is not None and not ov.is_empty()) else None


def _layout_workflow(rules, card) -> tuple[str, str]:
    """**工作流权威**版式段（不含本机覆盖）。"""
    asset_type = card.type

    # ── 场景 · 360° 全景基准（§4.6）──
    if asset_type == "environment" and card.layout_variant == "panorama360":
        p = rules.panorama
        seg = (p.get("en") or "").replace(
            "[scene description]", _scene_keywords(card.scene_dna)).replace(
            "[场景描述]", _scene_keywords(card.scene_dna))
        layout = f"LAYOUT: {seg}"
        cons = ("CONSISTENCY: this panorama is the SPATIAL BASELINE for the scene — "
                "architecture, doors and windows, furniture, floor, light sources and the "
                "main spatial relationship must be locked, and all later angles (S01–S06) "
                "must be derived from it. Weather, time of day, characters, light state and "
                "prop placement may vary between later renders.")
        return layout, cons

    if asset_type == "environment":
        # ⚠️ 场景**不使用纯白背景**（§四 明文），故整段（含背景）都与前三类不同
        seg = _fill_scene_seg(rules.scene_en_segment, card.scene_dna)
        layout = f"LAYOUT: {seg}"
        cons = ("CONSISTENCY: lock architecture, doors and windows, furniture, floor, "
                "light sources and the main spatial relationship. Weather, time of day, "
                "present characters, light state and prop placement may vary. "
                "Never restructure the space without story reason.")
        return layout, cons

    if asset_type in ("expression", "pose"):
        sh = card.sheet_dna
        items = ", ".join(sh.items_en) or ", ".join(sh.items)
        if asset_type == "expression":
            layout = (f"LAYOUT: {sh.layout} grid, expression sheet, facial expressions, "
                      f"close-up portraits, {items}, grid layout, consistent character, "
                      f"clean white background")
            cons = ("CONSISTENCY: ONLY eyebrows, eyes, mouth, facial muscles and "
                    "micro-expressions may change between cells. Face shape, age, "
                    "hairstyle, hair colour, skin tone, eye colour and core identity "
                    "MUST stay identical in every cell. Do not redesign the person.")
        else:
            layout = (f"LAYOUT: {sh.layout}, pose sheet, multiple poses of the same "
                      f"character side by side, full body, {items}, consistent character")
            cons = ("CONSISTENCY: the same character in every pose — face, age, hairstyle, "
                    "body proportion and clothing state identical. Every pose must obey "
                    "anatomy, a real centre of gravity and plausible force chains; no broken "
                    "limbs, no reversed joints, no floating.")
        return layout, cons

    if asset_type == "costume":
        seg = rules.costume_en_segment
        layout = (f"LAYOUT: {seg}")
        cons = ("CONSISTENCY: all views must show exactly the same garment with identical "
                "cut, construction, layer order, colour, material, trim and degree of wear; "
                "flat garment presentation; do not redesign between views.")
        return layout, cons
    if asset_type == "prop":
        seg = rules.prop_en_segment
        layout = (f"LAYOUT: {seg} LEFT SIDE also carries a large hero view with mechanism "
                  "close-up; RIGHT SIDE: front, strict 90-degree side, back.")
        cons = ("CONSISTENCY: all views must show exactly the same prop with identical "
                "silhouette, dimensions, structural parts, colour, material, surface "
                "finish and wear. No hands, no usage scene, floating on neutral background.")
        return layout, cons

    # 角色 —— 用工作流的可拼接英文标准段做骨架，再补齐布局说明
    seg = rules.turnaround_en_segment
    layout = (
        "LAYOUT: professional 16:9 landscape character design sheet. "
        "LEFT SIDE: a large front-facing half-body portrait of the exact same character, "
        "emphasising facial identity, skin texture, eyes, hairstyle, clothing construction "
        "and material quality. "
        "RIGHT SIDE: three full-body views of the exact same character arranged "
        "horizontally — 1) STRICT FRONT VIEW, 2) STRICT 90-DEGREE SIDE VIEW, "
        f"3) STRICT BACK VIEW. Base standard: {seg}")
    cons = (
        "CONSISTENCY: the three views must depict exactly the same character with "
        "identical head-to-body ratio, proportions, facial identity, hairstyle, clothing, "
        "equipment count and positions, colours and materials. Equipment must appear in "
        "the same quantity, position and left/right relation in every view. "
        "Neutral standing pose: feet slightly apart, body upright, arms naturally down, "
        "no dynamic action, no combat pose. Do not redesign the character between views.")
    return layout, cons


def _tail_block(rules) -> str:
    """背景 / 光影 / 风格 / 质量 —— 光影与电影感取自工作流 §六。

    ⚠️ 全部走英文：`quality_params_en` 是 §六 4 项中文参数的英文映射，
    `cinematic_concrete` 取自权威文档 §49（原文即英文）。
    否则英文 prompt 里会夹中文，多数图像模型会忽略它们。
    """
    q_en = rules.quality_params_en
    cine = rules.cinematic_concrete or (
        "controlled key light, soft fill, subtle rim light, physically plausible "
        "falloff, controlled contrast, cinematic depth, restrained color palette")
    return (
        "BACKGROUND: pure white background or seamless white studio background, "
        "no environmental scene, no scenery, no props.\n"
        "LIGHTING: soft even studio lighting, subtle ambient illumination, soft contact "
        "shadow, no harsh shadows, cinematic lighting quality — so that fabric, skin, "
        "metal and leather read clearly.\n"
        f"CINEMATIC QUALITY (concrete, not just the word 'cinematic'): {cine}\n"
        f"STYLE: ultra-detailed photorealistic hyper-detailed character design, "
        f"professional game character design sheet. Quality targets: {q_en}."
    )


# ─────────────────────────────────────────────────────────────
# 组装
# ─────────────────────────────────────────────────────────────

def _identity_line(card: AssetCard) -> str:
    bits = []
    if card.age:
        bits.append(f"{card.age}-year-old")
    if card.gender:
        bits.append(card.gender)
    if card.world:
        bits.append(tr(card.world))
    if card.occupation:
        bits.append(OCCUPATION_EN.get(card.occupation, tr(card.occupation)))
    if card.camp:
        bits.append(f"({tr(card.camp)})")
    return " ".join(bits) or card.name or "character"


def _pl(pairs) -> str:
    """`[(en, cn), …]` → 每对二选一后拼接（**不是两个都拼**）。"""
    return _join(pick_list([p[0] for p in pairs], [p[1] for p in pairs]))


def _is_extra_name(card: AssetCard) -> bool:
    """名字是否包含「身份行没覆盖的额外信息」。

    自动生成的名字形如 `佣兵-wasteland`（职业-世界观），内容已被身份行覆盖 →
    不再拼到英文 prompt 里（避免留一串中文）。用户给的真名（如「艾米丽」）则保留。
    """
    name = (card.name or "").strip()
    if not name:
        return False
    auto = f"{card.occupation or '角色'}-{card.world or '未定'}"
    return name != auto


def _scene_tail_block(rules, sd) -> str:
    """场景的收尾段 —— **不能复用角色的 `_tail_block`**。

    ⚠️ 角色/道具段的背景是「pure white background … no scenery, no props」，
    而场景**恰恰需要**环境与景深（§四 明文「环境不使用纯白背景」）。
    若复用，会得到自相矛盾的 prompt（既要求纯白背景、又要求 cinematic environment）。
    """
    q_en = rules.quality_params_en
    cine = rules.cinematic_concrete or (
        "controlled key light, soft fill, subtle rim light, physically plausible "
        "falloff, controlled contrast, cinematic depth")
    parts = [
        f"LIGHTING: {sd.light_source_en or sd.light_source or 'one clear key light direction'}",
        f"TIME OF DAY: {sd.time_of_day_en or sd.time_of_day}" if (sd.time_of_day_en or sd.time_of_day) else "",
        f"WEATHER: {sd.weather_en or sd.weather}" if (sd.weather_en or sd.weather) else "",
        f"CINEMATIC QUALITY (concrete, not just the word 'cinematic'): {cine}",
        f"STYLE: cinematic environment concept art, production design quality, "
        f"ultra-high detail. Quality targets: {q_en}.",
    ]
    return "\n".join(p for p in parts if p)


def build_prompt_en(card: AssetCard, rules) -> str:
    vd, ff, sv = card.visual_dna, card.fixed_features, card.stage_variables
    layout, cons = _layout_block(rules, card)

    # ── 场景（ENV_）：字段与其它三类完全不同，用 SceneDNA ──
    if card.type == "environment":
        sd = card.scene_dna
        pano = card.layout_variant == "panorama360"
        parts = [
            ("Create a 360° equirectangular panorama of a cinematic environment for an "
             "AI-animation / game production art library — this is the SPATIAL BASELINE of "
             "the scene, from which all later camera angles are derived."
             if pano else
             "Create a professional cinematic ENVIRONMENT concept design for an "
             "AI-animation / game production art library."),
            f"SCENE: {pick(sd.name_en, card.name) or 'environment'}"
            + (f" ({tr(card.world)})" if card.world else ""),
            "ARCHITECTURE: " + _join([pick(sd.building_en, sd.building),
                                      pick(sd.architectural_style_en, sd.architectural_style)]),
            "SPACE & SCALE: " + _join([pick(sd.spatial_scale_en, sd.spatial_scale),
                                       pick(sd.scale_vs_character, "")]),
            "MATERIALS: " + pick(sd.materials_en, sd.materials),
            "ATMOSPHERE: " + pick(sd.atmosphere_en, sd.atmosphere),
            "ERA: " + pick(sd.era_en, sd.era),
            "CIRCULATION: " + pick(sd.circulation_en, sd.circulation),
            "FOREGROUND / MIDGROUND / BACKGROUND: " + _join([
                pick(sd.foreground_en, sd.foreground),
                pick(sd.midground_en, sd.midground),
                pick(sd.background_en, sd.background)]),
            "SET DRESSING: " + pick(sd.props_in_scene_en, sd.props_in_scene),
            "COLOR: " + pick(sd.primary_color_en, sd.primary_color),
            "MULTI-ANGLE LOCK: " + ", ".join(sd.locked_elements_en or sd.locked_elements)
            if (sd.locked_elements_en or sd.locked_elements) else "",
            "MAY VARY: " + ", ".join(sd.variable_elements_en or sd.variable_elements)
            if (sd.variable_elements_en or sd.variable_elements) else "",
            layout, cons, _scene_tail_block(rules, sd),
        ]
        return "\n".join(p for p in parts if p and not p.endswith(": "))

    # ── 服装（CST_）：**必须单独一支** ──
    # ⚠️ 原版没有这一支 → 服装 prompt 走角色分支，开头写成
    #    「character design sheet」、STYLE 写成「character design」，
    #    对一件衣服来说是错的（实测踩到）。
    if card.type == "costume":
        parts = [
            "Create a professional 16:9 landscape COSTUME design sheet for a cinematic "
            "AI-animation / game production asset library.",
            f"GARMENT: {card.name or 'garment'}"
            + (f" ({tr(card.world)})" if card.world else ""),
            "LAYERS: " + pick(vd.layers_en, vd.layers),
            "SILHOUETTE: " + pick(vd.silhouette_en, vd.silhouette),
            "MATERIALS: " + _pl([(vd.material_en, vd.material),
                                 (vd.surface_texture_en, vd.surface_texture)]),
            "CONSTRUCTION: " + pick(vd.structure_en, vd.structure),
            "COLOUR: " + pick(vd.primary_color_en, vd.primary_color),
            "WEAR: " + pick(vd.wear_en, vd.wear),
            "ACCESSORIES: " + pick(vd.signature_accessory_en, vd.signature_accessory),
            layout, cons, _tail_block(rules),
        ]
        return "\n".join(p for p in parts if p and not p.endswith(": "))

    # ── 表情集 / 动作集（EXP_ / POS_）：挂在角色上，锚点必须写满 ──
    if card.type in ("expression", "pose"):
        sh = card.sheet_dna
        head = ("Create a professional expression sheet for a cinematic AI-animation "
                "character asset library." if card.type == "expression" else
                "Create a professional pose sheet for a cinematic AI-animation "
                "character asset library.")
        parts = [
            head,
            f"SUBJECT: {sh.owner or card.name or 'character'}",
            # ⚠️ 只给**英文** ITEMS —— 曾同时输出 CN `ITEMS:` 与 `ITEMS (EN):`，
            #    前者把整张中文表塞进了英文 prompt（实测：动作集 175 字）。
            "ITEMS: " + (" · ".join(sh.items_en or sh.items)),
            "CONSISTENCY CONSTRAINTS (must NOT change): " + ", ".join(sh.consistency_anchors),
            "MUTABLE (only these may change): "
            + ", ".join(sh.mutable_parts_en or sh.mutable_parts),
        ]
        if card.type == "expression":
            parts.append("IRON RULE: only eyebrows, eyes, mouth, facial muscles and "
                         "micro-expressions change; face shape, age, hairstyle, hair "
                         "colour and core identity are FIXED.")
        else:
            # ⚠️ 用英文版（`physics_checks_en`）—— 中文版会往英文 prompt 里塞整段中文
            parts.append("PHYSICS CHECKS (must all hold): "
                         + " | ".join(sh.physics_checks_en or sh.physics_checks))
            if sh.clothing_state:
                parts.append(f"CLOTHING STATE: {sh.clothing_state}")
            if sh.prop_ids:
                parts.append("PROP REFERENCES: " + ", ".join(sh.prop_ids))
        parts += [layout, cons, _tail_block(rules)]
        return "\n".join(p for p in parts if p and not p.endswith(": "))


    if card.type == "prop":
        parts = [
            "Create a professional 16:9 landscape prop design sheet for a cinematic "
            "AI-animation / game production asset library.",
            f"PROP: {card.name or 'prop'}"
            + (f" ({OCCUPATION_EN.get(card.occupation, tr(card.occupation))})"
               if card.occupation else ""),
            "STRUCTURE: " + _pl([(vd.structure_en, vd.structure),
                                 (vd.craft_en, vd.craft)]),
            "MATERIALS: " + _pl([(vd.material_en, vd.material),
                                 (vd.surface_texture_en, vd.surface_texture)]),
            "WEAR: " + pick(vd.wear_en, vd.wear),
            "COLOR: " + pick(vd.primary_color_en, vd.primary_color),
            "SCALE: " + pick(vd.scale_reference_en, vd.scale_reference),
            layout, cons, _tail_block(rules),
        ]
        return "\n".join(p for p in parts if p and not p.endswith(": "))

    parts = [
        "Create a professional 16:9 landscape character design sheet for a cinematic "
        "AI-animation / game production asset library.",
        # ⚠️ 名字后缀只在「非纯推导」时才加 —— 自动生成的名字形如 `佣兵-wasteland`，
        #    内容已被身份行完全覆盖；再拼上去只会在英文 prompt 里留一串中文。
        f"CHARACTER: {_identity_line(card)}"
        + (f" — {card.name}" if _is_extra_name(card) else ""),
        # ⚠️ 不重复 ff.facial_contour —— 它是由 face_shape + jaw 推导出的摘要，
        #    一起写会让 prompt 出现 "strong jaw, hollow cheeks" 两遍。
        "FACE: " + _pl([(vd.face_shape_en, vd.face_shape), (vd.jaw_en, vd.jaw),
                        (vd.brow_ridge_en, vd.brow_ridge),
                        (vd.nose_bridge_en, vd.nose_bridge), (vd.lips_en, vd.lips)]),
        # ⚠️ 不再追加 ff.iris_color：它的内容就是 vd.eye_color（瞳孔色），
        #    `eye_color_en` 已覆盖；追加会输出未翻译的 `深褐`。
        "EYES: " + _pl([(vd.eye_shape_en, vd.eye_shape),
                        (vd.eye_color_en, vd.eye_color)]),
        "SKIN: " + pick(sv.skin_state_en, sv.skin_state),
        "DISTINCTIVE MARKS: " + _join(
            pick_list(ff.permanent_marks_en, ff.permanent_marks)),
        "HAIR: " + _pl([(vd.hair_length_en, vd.hair_length),
                        (vd.hair_style_en, vd.hair_style),
                        (vd.hair_volume_en, vd.hair_volume),
                        (vd.hair_color_en, vd.hair_color),
                        (vd.hair_parting_en, vd.hair_parting),
                        (vd.bangs_en, vd.bangs),
                        (sv.hairstyle_change_en, sv.hairstyle_change)]),
        "BODY: " + _pl([(vd.height_en, vd.height), (vd.body_type_en, vd.body_type),
                        (vd.shoulder_width_en, vd.shoulder_width),
                        (sv.physique_vibe_en, sv.physique_vibe)]),
        "CLOTHING: " + _pl([(vd.layers_en, vd.layers),
                            (vd.silhouette_en, vd.silhouette)]),
        "MATERIALS: " + _pl([(vd.material_en, vd.material),
                             (vd.surface_texture_en, vd.surface_texture)]),
        "EQUIPMENT: " + _pl([(vd.signature_accessory_en, vd.signature_accessory),
                             (sv.core_accessories_en, sv.core_accessories)]),
        "COLOR PALETTE: " + _join(pick_list(
            [vd.primary_color_en] + list(vd.palette4_en),
            [vd.primary_color])),
        "SIGNATURE POINTS: " + _join(
            pick_list(vd.signature_points_en, vd.signature_points)),
        layout, cons, _tail_block(rules),
    ]
    return "\n".join(p for p in parts if p and not p.endswith(": "))


def build_prompt_cn(card: AssetCard) -> str:
    vd = card.visual_dna

    # ── 场景（ENV_）──
    if card.type == "environment":
        sd = card.scene_dna
        pano = card.layout_variant == "panorama360"
        lines = [
            ("【场景空间基准 · 360° 全景】等距柱状投影，用于确定空间完整布局"
             if pano else
             "【场景资产图】电影级环境概念设计，用于 AI 漫剧资产库"),
            f"场景：{' / '.join(x for x in [card.name, tr(card.world)] if x)}",
            f"建筑：{_join([sd.building, sd.architectural_style])}",
            f"空间与尺度：{_join([sd.spatial_scale, sd.scale_vs_character])}",
            f"材料：{sd.materials}",
            f"光线：{sd.light_source}",
            f"氛围：{sd.atmosphere}",
            f"时代：{sd.era}",
            f"动线：{sd.circulation}",
            f"前中后景：{_join([sd.foreground, sd.midground, sd.background])}",
            f"陈设：{sd.props_in_scene}",
            f"配色：{sd.primary_color}",
            f"多角度锁定：{' / '.join(sd.locked_elements)}",
            f"允许变化：{' / '.join(sd.variable_elements)}",
            "⚠️ 背景：**不使用纯白背景**（场景与角色/道具的核心区别）",
            "版式：单张电影级环境图，前景 / 中景 / 后景分层清晰，空间可读",
            "品质：8K 超清、影视级场景概念设计质感",
        ]
        return "\n".join(x for x in lines if x and not x.endswith("："))

    # ── 表情集 / 动作集 ──
    if card.type in ("expression", "pose"):
        sh = card.sheet_dna
        is_exp = card.type == "expression"
        lines = [
            f"【{'表情集' if is_exp else '动作集'}】用于 AI 漫剧资产库",
            f"所属角色：{sh.owner or '（未指定）'}",
            f"表项（{len(sh.items)} 项{'，基线' if sh.is_baseline else ''}）："
            f"{' / '.join(sh.items)}",
            f"版式：{sh.layout}",
            f"一致性锚点（**绝不允许变**）：{' / '.join(sh.consistency_anchors)}",
            f"允许改变：{' / '.join(sh.mutable_parts)}",
        ]
        if is_exp:
            lines += [
                "铁律：只改 眉 / 眼 / 嘴 / 面部肌肉 / 微表情",
                "⚠️ 脸型 / 年龄 / 发型 / 发色 / 核心身份 **保持不变**（否则等于换人）",
                "背景：纯净背景，便于裁剪单格",
            ]
        else:
            lines += [
                f"动作必须符合：{' ； '.join(sh.physics_checks)}",
                f"服装状态：{sh.clothing_state or '（未指定，需与剧情阶段一致）'}",
                f"道具引用：{' / '.join(sh.prop_ids) or '（无）'}",
                "背景：纯净背景，同一角色多动作并排",
            ]
        lines.append("品质：8K 超清、拟真影视级")
        return "\n".join(x for x in lines if x and not x.endswith("："))

    role = {"character": "角色", "prop": "道具", "costume": "服装",
            "environment": "场景"}.get(card.type, "资产")
    lines = [
        f"【{role}资产图】16:9 横版设计稿，用于 AI 漫剧资产库",
        f"主体：{' / '.join(x for x in [str(card.age) + '岁' if card.age else '',
                                        card.gender, card.occupation, card.name] if x)}",
        f"面部：{_join([vd.face_shape, vd.jaw, vd.brow_ridge, vd.nose_bridge, vd.lips])}",
        f"眼睛：{_join([vd.eye_shape, vd.eye_color])}",
        f"发型：{_join([vd.hair_length, vd.hair_style, vd.hair_color, vd.bangs])}",
        f"体型：{_join([vd.height, vd.body_type, vd.shoulder_width])}",
        f"服装：{_join([vd.layers, vd.silhouette])}",
        f"材质：{_join([vd.material, vd.surface_texture])}",
        f"装备：{_join([vd.signature_accessory])}",
        f"配色：{vd.primary_color}",
        "版式：左侧半身/头部特写（验五官与材质）；右侧正 / 严格 90° 侧 / 背 三视图",
        "一致性：三视图必须同一角色，头身比 / 服装 / 装备 / 配色 / 材质完全一致",
        "姿态：自然站立，双脚微开，双臂自然下垂，不做剧情动作",
        "背景：纯白或极浅灰影棚背景，无环境叙事",
        "光影：柔和均匀棚拍光，无强烈硬阴影，便于辨认材质",
        "品质：8K 超清、拟真影视级概念设计稿质感",
    ]
    return "\n".join(x for x in lines if x and not x.endswith("："))


def build_prompts(card: AssetCard, rules, *, failures: list[str] | None = None
                  ) -> tuple[str, str, str]:
    """生成并**回填**到 card：(prompt_en, prompt_cn, negative)。

    负面词分两层叠加（依负面词库 §五·1「默认全量追加」）：
      ① 工作流的负面词库（通用 + 模块 + 三视图）
      ② 文字屏蔽强制段（含权重 `(any text:1.8)`，§1.6 强调缺它无效）
    `failures` 传 FAILURE-00X 时再追加对应修复词（§五·2「只增不换」）。
    """
    cn = build_prompt_cn(card)
    en = build_prompt_en(card, rules)

    neg = rules.negative_for(card.type, failures)

    # 场景：追加 §四·4.5 场景负面词（与负面词库 §三 的场景组**是两处独立声明**）
    if card.type == "environment":
        for t in rules.scene_negative:
            if t and t not in neg:
                neg = f"{neg}, {t}"
        # 360° 全景：再追加 §4.6 的反向提示词。
        # ⚠️ 原文该块是**中英双写**的；生图用英文行 → 只取不含中文的项，
        #    否则会把整段中文负面词塞进英文 negative。
        if card.layout_variant == "panorama360":
            for t in (rules.panorama.get("negative") or "").split(","):
                t = t.strip()
                if t and not any("\u4e00" <= ch <= "\u9fff" for ch in t) and t not in neg:
                    neg = f"{neg}, {t}"

    # 表情 / 动作：追加库 §三 产线规范里的固定负面词
    if card.type == "expression":
        from .expression_agent import negative_extra
        neg = f"{neg}, {negative_extra()}"
    elif card.type == "pose":
        from .pose_agent import negative_extra
        neg = f"{neg}, {negative_extra()}"

    tb = rules.text_block_negative
    if tb and tb not in neg:
        neg = f"{neg}, {tb}"

    # ── 本机覆盖层（`prompts/overrides/`）──
    # ⭐ 只在**这一处**应用，理由：`build_prompt_en` 有 6 个 return 分支
    #    （角色/服装/道具/场景/全景/表情动作），逐个加必然漏一个 —— 那就成了
    #    「某类资产的覆盖不生效」这种最难查的静默 bug。
    ov = _ovr(rules)
    if ov is not None:
        for t in ov.negative_extra(card.type):
            if t and t not in neg:
                neg = f"{neg}, {t}"
        extra = ov.prompt_extra(card.type)
        if extra:
            # ⚠️ 表头必须**纯英文** —— 这里进的是英文 prompt。
            #    我自己第一版写成「（本机追加，来源 prompts/overrides/）」，
            #    于是角色英文段凭空多了 6 个中文字（这是本项目第 6 次同款问题）。
            en = f"{en}\n\nLOCAL OVERRIDE (appended by prompts/overrides/):\n{extra}"

    card.prompt_en, card.prompt_cn, card.negative_prompt = en, cn, neg
    return en, cn, neg


def build_source_prompt(card: AssetCard, rules, *, failures: list[str] | None = None,
                        provider: str = "generic") -> str:
    """按目标平台给最终 prompt 加「文字屏蔽」正向段（依负面词库 §五 各平台写法）。

    · MJ / Niji            → `--no ...` 参数
    · SD / FLUX            → 文本词表（由调用方写入 negative 字段）
    · GPT Image / 通用      → 自然语言禁止段
    · Seedance / 可灵      → 中文自然语言「禁止出现」
    """
    pos = rules.text_block_positive
    if provider in ("midjourney", "niji"):
        head = ", ".join(card.negative_prompt.split(", ")[:25])
        return f"{card.prompt_en} --no {head}"
    if provider in ("seedance", "kling"):
        return (f"{card.prompt_cn}\n\n【禁止出现】文字 · 字母 · Logo · 水印 · 字幕 · "
                f"随机符号 · 多余人形 · 多余肢体 · 服装不一致 · 装备不一致")
    if provider in ("openai", "gpt-image", "generic"):
        return f"{card.prompt_en}\n\nNO TEXT: {pos}"
    return card.prompt_en
