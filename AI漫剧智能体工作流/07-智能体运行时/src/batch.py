# -*- coding: utf-8 -*-
"""批量生产 —— 蓝图 §十八。

蓝图原文（只给了行为，没给实现约束）：

    未来支持：一次生成 10 个废土 NPC。
    Agent 自动：CHAR-001 / CHAR-002 / … / CHAR-010
    每个角色**独立生成**：JSON · Prompt · Image · Metadata

⭐ **实现取向：不做"批量专用流水线"**，而是把「一次 10 个废土 NPC」
**展开成 10 条自然语言请求**，再各自走**正常创建流程**。

理由（这是本项目的既有纪律）：
  · 复用同一条路径 → 每项都自动获得一致的一致性 Gate / 指纹 / 版本 / 落盘，
    不会出现「批量生成的东西和单个生成的不一样」这种最难查的偏差；
  · 用户看得到每一条展开后的描述 → 不满意可直接复制去单独跑或手改；
  · 有 LLM 时由 LLM 出变体；**无 Key 时用本地池**，保证零依赖仍可跑。

⚠️ **难点是"不重复"**：`character_agent` 按世界观取预设，若照抄会生成 10 个一模一样的角色。
   故本模块的职责就是**给每一项分配不同的身份/年龄/识别点**。
"""

from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────
# NPC 池 —— 按世界观分组的「职业 / 识别点 / 年龄」
# 池子长度 ≥ 10，保证 `--count 10` 不重复（超出的按取模复用并追加序号）
# ─────────────────────────────────────────────────────────────
NPC_POOLS: dict[str, dict] = {
    "wasteland": {
        "cn": "废土",
        "jobs": ["拾荒者", "商队护卫", "水泵工", "清道夫", "佣兵",
                 "战地医生", "机械师", "哨兵", "走私贩", "流浪艺人"],
        "features": ["风沙磨花的护目镜", "缝合的皮革臂套", "背负式滤水罐",
                     "锈蚀的右侧义肢", "缠满胶带的旧步枪", "挂在颈间的辐射计",
                     "补丁摞补丁的围巾", "铁丝缠绕的护膝", "半张烧毁的面罩",
                     "一只报时的旧怀表"],
        "ages": [22, 28, 34, 41, 19, 55, 37, 26, 48, 31],
    },
    "cyberpunk": {
        "cn": "赛博朋克",
        "jobs": ["赏金猎人", "义体医生", "数据窃贼", "夜店老板", "街头黑客",
                 "快递骑手", "义体拳手", "黑市贩子", "私人侦探", "修械师"],
        "features": ["颈后数据接口", "发光瞳孔", "机械义指", "皮下植入纹路",
                     "半透明义肢外壳", "耳后散热片", "全息投影纹身",
                     "外露脊椎排线", "下颌合金补片", "手腕接线端口"],
        "ages": [25, 33, 29, 44, 21, 38, 27, 51, 35, 30],
    },
    "scifi": {
        "cn": "科幻",
        "jobs": ["舰载工程师", "导航员", "医生", "陆战队员", "通讯官",
                 "科研员", "驾驶员", "安全官", "地质勘探员", "补给官"],
        "features": ["磁力靴", "腕载终端", "背挂式生命维持包", "颈部散热环",
                     "识别胸牌", "抗荷服束带", "腰间工具挂架", "眼部光学增强器",
                     "肩部通讯天线", "便携采样箱"],
        "ages": [31, 27, 40, 24, 36, 45, 29, 34, 52, 26],
    },
    "fantasy": {
        "cn": "奇幻",
        "jobs": ["游侠", "炼金术士", "雇佣剑士", "吟游诗人", "教士",
                 "盗贼", "猎魔人", "草药师", "铁匠", "占星师"],
        "features": ["斗篷兜帽", "腰间药瓶袋", "符文护腕", "背挂长弓",
                     "悬挂的圣徽", "蒙面布巾", "银质吊坠", "皮革卷轴筒",
                     "铁匠围裙", "星盘挂饰"],
        "ages": [26, 43, 32, 24, 50, 21, 38, 47, 35, 29],
    },
    "default": {
        "cn": "通用",
        "jobs": ["主角", "伙伴", "对手", "导师", "路人甲",
                 "店主", "守卫", "信使", "工匠", "旅人"],
        "features": ["标志性围巾", "随身旧物", "磨损的随身包", "一枚戒指",
                     "肩上的伤疤", "别在衣襟的徽章", "老旧的怀表", "手写的信笺",
                     "木柄工具", "磨破的袖口"],
        "ages": [24, 32, 29, 41, 19, 55, 36, 27, 46, 33],
    },
}

# 输入里的数量：「10个」「十个人」…
_CN_DIGIT = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def pool_for(world: str) -> dict:
    """取世界观对应的 NPC 池（认不出就用通用池）。"""
    w = (world or "").lower()
    for k, v in NPC_POOLS.items():
        if k != "default" and k in w:
            return v
    return NPC_POOLS["default"]


def parse_count(text: str, default: int = 10) -> int:
    """从输入里取数量（「一次生成10个」→ 10）。取不到用 default。"""
    m = re.search(r"(\d{1,2})\s*个", text or "")
    if m:
        return max(1, min(60, int(m.group(1))))
    m = re.search(r"([一二两三四五六七八九十])个", text or "")
    if m:
        return _CN_DIGIT.get(m.group(1), default)
    return default


# 这批词是"容器"不是"内容" —— 留着会让生成文本变成
# 「一个28岁的**废土NPC**商队护卫」（粘成一团），也让职业抽取取错
_NOISE = ("NPC", "npc", "Npc", "角色", "人物", "群像", "们")


def _strip_count(text: str) -> str:
    """去掉数量词与容器词，只留「世界观 + 题材」这类真正的内容。

    ⚠️ 必须去掉 `NPC` —— 否则生成的是「一个28岁的废土NPC商队护卫」，
    职业抽取（`_find_occupation`）的兜底正则会取到句尾修饰词而非职业（实测踩到）。
    """
    t = re.sub(r"(\d{1,2}|[一二两三四五六七八九十])\s*个", "", text or "")
    t = re.sub(r"一次(生成|做|建|批量)?", "", t)
    for w in _NOISE:
        t = t.replace(w, "")
    return t.strip(" ，,。的")


def plan(text: str, count: int = 0, asset_type: str = "character",
         world: str = "") -> list[dict]:
    """把一次批量请求**展开**成 N 条独立请求。

    返回 `[{ "text": …, "label": …, "index": n }, …]`。

    展开规则（按资产类型不同）：
      · 角色 / NPC → 分配不同**职业 + 识别点 + 年龄**
      · 场景      → 分配不同**场景名词**（同一世界观的多个空间）
      · 道具      → 分配不同**品类**
      · 服装 / 表情 / 动作 → 批量意义不大，仍按序号区分（提示用户）
    """
    n = count or parse_count(text)
    base = _strip_count(text)
    items: list[dict] = []

    if asset_type == "character":
        pool = pool_for(world or base)
        for i in range(n):
            job = pool["jobs"][i % len(pool["jobs"])]
            feat = pool["features"][i % len(pool["features"])]
            age = pool["ages"][i % len(pool["ages"])]
            # 超出池长时补序号，保证不重名
            suffix = f"（第{i // len(pool['jobs']) + 1}批）" if i >= len(pool["jobs"]) else ""
            items.append({
                "index": i + 1,
                "label": f"{age}岁 · {job}{suffix}",
                "text": f"一个{age}岁的{base or pool['cn']}{job}{suffix}，{feat}",
            })
    elif asset_type == "environment":
        pool = ["地下指挥中心", "废弃街区", "城郊公路", "临时营地", "水泵站",
                "医疗帐篷", "修理厂", "哨塔", "集市", "地下通道"]
        for i in range(n):
            space = pool[i % len(pool)]
            items.append({
                "index": i + 1,
                "label": space,
                "text": f"{base or ''}的{space}".lstrip("的"),
            })
    elif asset_type == "prop":
        pool = ["能源步枪", "多功能工具刀", "便携净水器", "信号发生器", "护目镜",
                "战术背包", "医疗箱", "燃料罐", "对讲机", "工具箱"]
        for i in range(n):
            p = pool[i % len(pool)]
            items.append({"index": i + 1, "label": p, "text": f"设计一个{p}"})
    else:
        # 服装 / 表情 / 动作：批量意义有限，仍按序号区分并在 CLI 里提示
        for i in range(n):
            items.append({
                "index": i + 1,
                "label": f"{base or asset_type} #{i + 1}",
                "text": f"{base}（第 {i + 1} 件）",
            })
    return items


def roster(results: list[dict]) -> str:
    """产出「花名册」—— 蓝图 §十八 要求列出自动分配的 ID。"""
    rows = ["| # | ID | 名称 | 版本 | 状态 |", "|---|---|---|---|---|"]
    ok = 0
    for r in results:
        if r.get("ok") is False or "asset_id" not in r:
            rows.append(f"| {r.get('index', '?')} | ❌ | "
                        f"{r.get('error', '失败')[:40]} | — | — |")
            continue
        ok += 1
        rows.append(f"| {r.get('index', '?')} | `{r['asset_id']}` | "
                    f"{r.get('name', '')[:20]} | {r.get('version', '')} | "
                    f"{r.get('status', '')} |")
    head = (f"共 {len(results)} 项，成功 **{ok}** 项"
            + (f"，失败 {len(results) - ok} 项" if ok < len(results) else ""))
    return head + "\n\n" + "\n".join(rows)
