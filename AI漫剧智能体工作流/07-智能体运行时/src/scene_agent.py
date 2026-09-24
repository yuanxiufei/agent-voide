# -*- coding: utf-8 -*-
"""场景 Agent —— `ENV_` 资产（环境/场景）。

权威依据（**只读**，不复制规则）：
  · `02-服化道/引擎/TURNAROUND-STANDARD.md` §四 场景标准（§09）
      —— 11 项必须生成要素 · 一致性要求 · 多角度空间逻辑 · 可拼接英文标准段 · 场景负面词
  · `02-服化道/00-主控智能体.md` §09 ENVIRONMENT ENGINE / §32 场景连续性
  · `02-服化道/引擎/PROMPT-TEMPLATES.md` §37 默认环境输出协议 + 五·补 场景快速公式

⚠️ **场景与前三类资产的核心区别**：**环境不使用纯白背景**（§四 开头明文）。
   故版式、英文段、负面词三处都与角色/道具不同 —— 负面词由 `rule_source.negative_for
   ("environment")` 自动叠加「场景」组，且**不加三视图负面词**（场景没有三视图）。
"""

from __future__ import annotations

from .schema import AssetCard, SceneDNA

# ─────────────────────────────────────────────────────────────
# 场景预设 —— 每条覆盖 §四·4.1 的 11 项必须生成要素
# 字段顺序：建筑 / 空间尺度 / 材料 / 光线 / 氛围 / 时代 / 人物动线 /
#           前景 / 中景 / 后景 / 建筑风格
# ─────────────────────────────────────────────────────────────

SCENE_PRESETS: list[dict] = [
    {
        "keys": ["指挥中心", "控制室", "指挥部", "舰桥"],
        "name": "指挥中心",
        "cn": {
            "building": "环形指挥大厅，中央下沉式主控台，环绕式大屏阵列",
            "spatial_scale": "层高约 8 米，可容纳 30 人同时作业",
            "materials": "冷轧钢板墙体、防眩光玻璃隔断、磨砂金属台面",
            "light_source": "顶部线性冷白主光 + 屏幕自发光作为副光，光源方向自上而下",
            "atmosphere": "紧张、克制、信息密集",
            "era": "近未来",
            "circulation": "主控台为中心，人员沿环形通道单向流动",
            "foreground": "主控台边缘与散落的纸质任务书",
            "midground": "操作员工位与大屏阵列",
            "background": "环形走廊与安全门",
            "style": "工业未来主义，功能优先、无明显装饰",
        },
        "en": {
            "building": "circular command hall, sunken central console, wraparound screen wall",
            "spatial_scale": "about 8m ceiling height, room for 30 operators",
            "materials": "cold-rolled steel walls, anti-glare glass partitions, brushed metal desks",
            "light_source": "linear cool-white key light from above, screen glow as fill, top-down direction",
            "atmosphere": "tense, restrained, information-dense",
            "era": "near future",
            "circulation": "console at the centre, staff moving one-way along the ring corridor",
            "foreground": "console edge, scattered paper briefing sheets",
            "midground": "operator stations and screen array",
            "background": "ring corridor and security doors",
        },
    },
    {
        "keys": ["废墟", "废土", "残骸", "遗迹"],
        "name": "废土废墟",
        "cn": {
            "building": "坍塌的混凝土建筑残骸，裸露钢筋与断墙",
            "spatial_scale": "开阔街区尺度，残墙高约 6–12 米",
            "materials": "风化混凝土、锈蚀钢筋、积沙与碎砾",
            "light_source": "低角度暖橙阳光斜射，穿过断墙形成长阴影与尘埃光束",
            "atmosphere": "荒凉、死寂、被遗弃",
            "era": "灾后 20 年",
            "circulation": "沿瓦砾间被踩出的窄径曲折穿行",
            "foreground": "半埋的轮胎与破碎路牌",
            "midground": "倾斜的楼体骨架与倒塌的广告牌",
            "background": "沙尘中的远景天际线与更多废墟剪影",
            "style": "粗野主义残骸 + 后启示录",
        },
        "en": {
            "building": "collapsed concrete ruins, exposed rebar and sheared walls",
            "spatial_scale": "open street scale, broken walls 6-12m tall",
            "materials": "weathered concrete, rusted rebar, drifted sand and rubble",
            "light_source": "low warm-orange sunlight raking across broken walls, long shadows and dust shafts",
            "atmosphere": "desolate, silent, abandoned",
            "era": "20 years after the fall",
            "circulation": "narrow trodden paths winding between rubble",
            "foreground": "half-buried tyres and a broken street sign",
            "midground": "leaning building skeletons, toppled billboards",
            "background": "distant skyline in dust haze, more ruin silhouettes",
        },
    },
    {
        "keys": ["街道", "市区", "都市", "霓虹", "赛博"],
        "name": "赛博都市街道",
        "cn": {
            "building": "高层密排楼体，外挂管道与全息广告牌",
            "spatial_scale": "窄巷宽约 6 米，两侧楼高 40 米以上",
            "materials": "湿沥青、金属格栅、亚克力灯箱、雾面玻璃",
            "light_source": "霓虹招牌自发光为主光，地面积水反射形成下打光",
            "atmosphere": "拥挤、潮湿、被商业光污染笼罩",
            "era": "赛博未来",
            "circulation": "沿街摊贩与行人形成密集双向流",
            "foreground": "积水倒影与散落的塑料包装",
            "midground": "摊贩棚架、蒸汽排口、行人剪影",
            "background": "雾气中层层退远的高楼与全息广告",
            "style": "高科技低生活，垂直分层",
        },
        "en": {
            "building": "dense high-rises with external pipework and holographic billboards",
            "spatial_scale": "narrow alley about 6m wide, buildings over 40m",
            "materials": "wet asphalt, metal grating, acrylic light boxes, fogged glass",
            "light_source": "neon signage as key, puddle reflections bouncing light from below",
            "atmosphere": "crowded, humid, drowned in commercial light pollution",
            "era": "cyber future",
            "circulation": "dense two-way flow of vendors and pedestrians",
            "foreground": "puddle reflections, scattered plastic wrappers",
            "midground": "vendor awnings, steam outlets, pedestrian silhouettes",
            "background": "receding towers and holograms in fog",
        },
    },
    {
        "keys": ["荒野", "沙漠", "雪原", "冰川", "荒原", "山林", "森林"],
        "name": "自然旷野",
        "cn": {
            "building": "无人工建筑，仅有自然的岩层与地势",
            "spatial_scale": "广袤开阔，地平线极低",
            "materials": "裸岩、冻土、枯草、积雪",
            "light_source": "大面积天光，方向明确，色温偏冷",
            "atmosphere": "辽阔、寂静、压制感",
            "era": "无时代标记",
            "circulation": "无明显路径，视线沿地势延伸至地平线",
            "foreground": "近处碎岩与被风吹弯的枯草",
            "midground": "起伏的岩脊与孤立的枯树",
            "background": "压低的云层与地平线",
            "style": "自然主义，去人工痕迹",
        },
        "en": {
            "building": "no man-made structures, only natural rock strata and terrain",
            "spatial_scale": "vast and open, very low horizon line",
            "materials": "bare rock, frozen soil, dry grass, snow",
            "light_source": "broad skylight, clear direction, cool colour temperature",
            "atmosphere": "expansive, silent, oppressive",
            "era": "no era markers",
            "circulation": "no defined path, sightline follows terrain to the horizon",
            "foreground": "close broken rocks and wind-bent dry grass",
            "midground": "rolling rock ridges and an isolated dead tree",
            "background": "lowered cloud deck and the horizon",
        },
    },
    {
        "keys": ["飞船", "太空", "空间站", "舱", "实验室"],
        "name": "太空舱内",
        "cn": {
            "building": "胶囊式舱室，环形加强肋与设备舱壁",
            "spatial_scale": "狭窄，约 3 米宽 × 2.4 米高",
            "materials": "拉丝铝合金舱壁、哑光白色面板、织带固定件",
            "light_source": "嵌入式冷白条灯，均匀无方向感",
            "atmosphere": "洁净、封闭、机械感",
            "era": "远未来",
            "circulation": "单轴向通行，需借助舱壁扶手",
            "foreground": "舱门密封环与地面滑轨",
            "midground": "设备机柜与观察窗",
            "background": "通往下一舱段的舱门",
            "style": "功能主义航天器内装，零冗余装饰",
        },
        "en": {
            "building": "capsule cabin with ring stiffeners and equipment bulkheads",
            "spatial_scale": "cramped, about 3m wide by 2.4m high",
            "materials": "brushed aluminium bulkheads, matte white panels, webbing tie-downs",
            "light_source": "recessed cool-white strip lights, even and directionless",
            "atmosphere": "clean, enclosed, mechanical",
            "era": "far future",
            "circulation": "single-axis passage with handrails along the walls",
            "foreground": "hatch seal ring and floor rails",
            "midground": "equipment racks and a viewing port",
            "background": "hatch leading to the next section",
        },
    },
    {
        "keys": ["宫殿", "厅堂", "大殿", "古风", "府邸", "庭院"],
        "name": "古风殿宇",
        "cn": {
            "building": "木构架殿堂，重檐歇山顶，列柱与格扇门",
            "spatial_scale": "中轴对称，进深约 20 米，柱高 9 米",
            "materials": "朱漆木柱、青石地面、青瓦、绢纱窗",
            "light_source": "侧向天光透过格扇形成规律光斑 + 烛火辅助暖光",
            "atmosphere": "肃穆、威压、克制",
            "era": "架空古代",
            "circulation": "沿中轴直行至主位，两侧为臣属站位",
            "foreground": "石阶与丹陛",
            "midground": "列柱与两侧烛台",
            "background": "主位屏风与藻井",
            "style": "东方古典官式建筑",
        },
        "en": {
            "building": "timber-frame hall, double-eave hip roof, colonnade and lattice doors",
            "spatial_scale": "axial symmetry, 20m deep, 9m columns",
            "materials": "red-lacquered timber columns, bluestone floor, grey tiles, silk lattice screens",
            "light_source": "side daylight through lattice casting regular light patches, candlelight as warm fill",
            "atmosphere": "solemn, imposing, restrained",
            "era": "fictional antiquity",
            "circulation": "axial approach to the seat of honour, retainers along both sides",
            "foreground": "stone steps and the raised ceremonial ramp",
            "midground": "colonnade and flanking candle stands",
            "background": "the seat screen and coffered ceiling",
        },
    },
    {
        "keys": ["战场", "战壕", "阵线", "炮火"],
        "name": "战场",
        "cn": {
            "building": "临时工事与掩体，弹坑与残破构筑",
            "spatial_scale": "开阔交战区，纵深数百米",
            "materials": "湿泥、沙袋、断木、弹壳与铁丝网",
            "light_source": "低平冷光 + 远处火光间歇性照亮烟尘",
            "atmosphere": "压抑、危险、硝烟弥漫",
            "era": "近现代战争",
            "circulation": "沿战壕横向机动，开阔地带低姿匍匐",
            "foreground": "泥浆中的弹壳与破损沙袋",
            "midground": "铁丝网、断树桩与掩体",
            "background": "升起的烟柱与被削平的地平线",
        },
        "en": {
            "building": "field fortifications and cover, craters and shattered structures",
            "spatial_scale": "open engagement zone several hundred metres deep",
            "materials": "wet mud, sandbags, splintered timber, shell casings, barbed wire",
            "light_source": "low flat daylight plus intermittent distant fire glow through smoke",
            "atmosphere": "oppressive, dangerous, smoke-choked",
            "era": "modern warfare",
            "circulation": "lateral movement along trenches, low crawling in the open",
            "foreground": "shell casings and burst sandbags in mud",
            "midground": "barbed wire, blasted stumps, cover",
            "background": "rising smoke columns and a flattened horizon",
        },
    },
    {
        "keys": ["地下", "洞穴", "隧道", "地窟"],
        "name": "地下空间",
        "cn": {
            "building": "人工开凿的岩壁通道，拱顶与支撑立柱",
            "spatial_scale": "通道宽约 4 米，拱高 5 米",
            "materials": "粗凿岩壁、渗水的石面、木质支撑",
            "light_source": "移动式人工光源（提灯/手电）为主，光域小而集中",
            "atmosphere": "幽闭、潮湿、未知",
            "era": "不定",
            "circulation": "沿主通道单向深入，岔路处需辨认",
            "foreground": "地面水洼与碎石",
            "midground": "支撑立柱与墙面渗水痕",
            "background": "通道尽头的黑暗",
        },
        "en": {
            "building": "hand-cut rock passage, arched ceiling and support columns",
            "spatial_scale": "about 4m wide passage, 5m arch height",
            "materials": "rough-hewn rock face, seeping wet stone, timber props",
            "light_source": "portable man-made light (lantern/torch) as key, small concentrated pool",
            "atmosphere": "claustrophobic, damp, unknown",
            "era": "unspecified",
            "circulation": "single direction deeper along the main passage, junctions to navigate",
            "foreground": "puddles and loose stones",
            "midground": "support columns and seepage streaks on the walls",
            "background": "darkness at the end of the passage",
        },
    },
    {
        "keys": ["居所", "房间", "卧室", "客厅", "室内", "公寓"],
        "name": "居住空间",
        "cn": {
            "building": "常规居住单元，标准门窗与隔墙",
            "spatial_scale": "住宅尺度，层高 2.8 米",
            "materials": "乳胶漆墙面、木地板、布艺与金属家具",
            "light_source": "窗侧自然光为主，室内灯具为暖色副光",
            "atmosphere": "日常、私密、可辨识的生活痕迹",
            "era": "当代",
            "circulation": "围绕家具形成的日常活动路径",
            "foreground": "散落的个人物品",
            "midground": "主要家具与墙面陈设",
            "background": "窗户与通往其他房间的门",
        },
        "en": {
            "building": "ordinary residential unit, standard doors, windows and partitions",
            "spatial_scale": "domestic scale, 2.8m ceiling",
            "materials": "emulsion-painted walls, timber floor, fabric and metal furniture",
            "light_source": "window daylight as key, warm interior lamps as fill",
            "atmosphere": "lived-in, private, readable traces of daily life",
            "era": "contemporary",
            "circulation": "daily paths formed around the furniture",
            "foreground": "scattered personal belongings",
            "midground": "main furniture and wall décor",
            "background": "the window and the door to other rooms",
        },
    },
]

# 预设的**英文名与建筑风格** —— key 必须与 `SCENE_PRESETS[*]["name"]` 一一对应。
# 单独成表的原因：`style` 只在各预设的 `cn` 里有，`en` 里若忘了加，
# 英文 prompt 就会回退成中文（实测踩到：EN prompt 里夹了 55 个中文字）。
SCENE_EN: dict[str, tuple[str, str]] = {
    "指挥中心": ("command centre", "industrial futurism, function-first, no ornament"),
    "废土废墟": ("wasteland ruins", "brutalist ruin, post-apocalypse"),
    "赛博都市街道": ("cyber city street", "high tech, low life, vertically stratified"),
    "自然旷野": ("open wilderness", "naturalistic, no man-made traces"),
    "太空舱内": ("spacecraft cabin", "functional spacecraft interior, zero redundant ornament"),
    "古风殿宇": ("ancient hall", "East-Asian classical official architecture"),
    "战场": ("battlefield", "modern field conditions, utilitarian"),
    "地下空间": ("underground passage", "rough excavation, utilitarian"),
    "居住空间": ("residence interior", "ordinary domestic interior"),
    "通用场景": ("environment", "architecture consistent with the VISUAL_BIBLE"),
}


DEFAULT_SCENE = {
    "name": "通用场景",
    "cn": {
        "building": "符合世界观的主要建筑体",
        "spatial_scale": "与角色身高比例相符的空间尺度",
        "materials": "与世界观相符的主导材料",
        "light_source": "单一明确的主光源方向，性质与氛围匹配",
        "atmosphere": "与剧情情绪一致的氛围",
        "era": "与世界观一致的时代",
        "circulation": "人物在空间中可读的动线",
        "foreground": "近景层，提供尺度参照",
        "midground": "中景层，主体空间关系",
        "background": "远景层，天际线或纵深",
        "style": "与 VISUAL_BIBLE 一致的建筑风格",
    },
    "en": {
        "building": "primary architecture matching the world bible",
        "spatial_scale": "spatial scale consistent with character height",
        "materials": "dominant materials consistent with the world",
        "light_source": "one clear key light direction, quality matched to the mood",
        "atmosphere": "atmosphere consistent with the story beat",
        "era": "era consistent with the world",
        "circulation": "readable path of movement through the space",
        "foreground": "near layer providing scale reference",
        "midground": "mid layer carrying the main spatial relationship",
        "background": "far layer, skyline or depth",
        "style": "architectural style consistent with the VISUAL_BIBLE",
    },
}

# §32 场景连续性：「同一场景建立后锁定 / 允许变化」——**所有场景共用**
LOCKED_BY_DEFAULT = ["建筑", "门窗", "家具", "地面", "光源", "主空间关系"]
VARIABLE_BY_DEFAULT = ["天气", "时间", "人物", "灯光状态", "道具摆放"]

# 上述两项的英文（进 English prompt；否则英文 prompt 里会留一串中文）
ELEMENT_EN = {
    "建筑": "architecture", "门窗": "doors and windows", "家具": "furniture",
    "地面": "floor", "光源": "light sources", "主空间关系": "main spatial relationship",
    "天气": "weather", "时间": "time of day", "人物": "present characters",
    "灯光状态": "light state", "道具摆放": "prop placement",
}


def _pick_preset(text: str) -> dict:
    for p in SCENE_PRESETS:
        if any(k in text for k in p["keys"]):
            return p
    return DEFAULT_SCENE


def complete(card: AssetCard, parsed, rules=None, llm=None) -> tuple[AssetCard, list[str]]:
    """补全场景字段。签名与其余 agent **一致**（`complete(card, parsed, rules, llm)`），
    这样 `agent.py` 里才能统一调用。"""
    notes = _fill(card, parsed)
    return card, notes


def _fill(card: AssetCard, parsed) -> list[str]:
    """补全场景字段（§四·4.1 的 11 项 + §32 的锁定/可变项）。返回说明。"""
    notes: list[str] = []
    preset = _pick_preset(parsed.raw)
    sd: SceneDNA = card.scene_dna

    for fld, val in preset["cn"].items():
        name = "architectural_style" if fld == "style" else fld
        if not getattr(sd, name, ""):
            setattr(sd, name, val)
        en = preset["en"].get(fld, "")
        if en and not getattr(sd, name + "_en", ""):
            setattr(sd, name + "_en", en)

    # 英文名与建筑风格（`SCENE_EN` 表；缺失则回退中文）
    name_en, style_en = SCENE_EN.get(preset["name"], ("", ""))
    if name_en and not sd.name_en:
        sd.name_en = name_en
    if style_en and not sd.architectural_style_en:
        sd.architectural_style_en = style_en

    # ⚠️ 场景**不设纯白背景**（§四 明文），故 layout 由 prompt_engine 单独给
    if not sd.locked_elements:
        sd.locked_elements = list(LOCKED_BY_DEFAULT)
    if not sd.locked_elements_en:
        sd.locked_elements_en = [ELEMENT_EN.get(e, e) for e in sd.locked_elements]
    if not sd.variable_elements:
        sd.variable_elements = list(VARIABLE_BY_DEFAULT)
    if not sd.variable_elements_en:
        sd.variable_elements_en = [ELEMENT_EN.get(e, e) for e in sd.variable_elements]

    # ⚠️ 陈设**故意不填占位符** —— 之前填了「（待与 PROP INDEX 对齐后填入）」，
    #    结果这串中文进了英文 prompt。留空则 prompt 自然跳过该行，提示改走 notes。
    if not sd.props_in_scene:
        notes.append("陈设道具留空 —— 建议与 `PRP_` 资产卡对齐后手动补 "
                     "`props_in_scene`（§四·4.2 要求与 PROP INDEX 一致）")

    # 用户输入里的色彩偏好 → 主色
    if parsed.color_hints and not sd.primary_color:
        sd.primary_color = parsed.color_hints[0]

    notes.append(f"场景类型：{preset['name']}")
    notes.append("必须生成要素 11 项已补齐（建筑/空间/材料/光线/氛围/时代/动线/前中后景/风格）")
    notes.append(f"多角度锁定 {len(sd.locked_elements)} 项 · 允许变化 {len(sd.variable_elements)} 项")
    if sd.primary_color:
        notes.append(f"主色调：{sd.primary_color}")
    return notes


def build_card(parsed: Parsed, asset_id: str, now: str) -> AssetCard:
    preset = _pick_preset(parsed.raw)
    return AssetCard(
        id=asset_id, type="environment",
        name=parsed.name or preset["name"],
        source=parsed.raw, created_at=now, updated_at=now,
        world=parsed.world,
        # 场景的「锁定项」= §32 的 6 项建筑空间要素
        locked=list(LOCKED_BY_DEFAULT),
    )
