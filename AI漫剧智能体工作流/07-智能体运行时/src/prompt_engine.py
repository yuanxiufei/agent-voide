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

def _layout_block(rules, asset_type: str) -> tuple[str, str]:
    """返回 (版式段, 一致性段)。三视图与服装/道具用各自的标准段。"""
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


def build_prompt_en(card: AssetCard, rules) -> str:
    vd, ff, sv = card.visual_dna, card.fixed_features, card.stage_variables
    layout, cons = _layout_block(rules, card.type)

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
    tb = rules.text_block_negative
    if tb and tb not in neg:
        neg = f"{neg}, {tb}"

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
