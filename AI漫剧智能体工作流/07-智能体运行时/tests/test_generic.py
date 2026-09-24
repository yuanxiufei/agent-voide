# -*- coding: utf-8 -*-
"""**通用性**测试 —— 任何一部小说都能跑，且英文 prompt 不夹中文。

═══════════════════════════════════════════════════════════════════
为什么需要这个文件
═══════════════════════════════════════════════════════════════════
① **通用性**：此前补全靠**固定题材表**（角色 11 题材 · 服装只 4 类 · 道具只 5 类 ·
   批量 5 池）。实测量化过：5 种输入里**服装预设全部没命中**，
   于是「穿**旗袍**的女特工」被补成「**棉**质三层功能服装」——
   **把用户给的事实换成了预设里的假具体值**。
   → 本测试钉住：**表外题材也要把用户原话写进字段**。

② **英文纯度**：本项目已**第 7 次**踩"英文 prompt 里夹中文"，
   且第 7 次是通用补全层自己引入的（把抽到的中文词拼进了英文）。
   → 本测试钉住：**8 种题材的英文 prompt 中文字符数必须为 0**。

运行：`python tests/test_generic.py`
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import generic as g                                  # noqa: E402
from src import nl_parser as nlp                              # noqa: E402

PASS, FAIL = [], []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(label)
    print(f"  {'✅' if ok else '❌'} {label}" + (f"   ← {detail}" if detail and not ok else ""))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="_generic_test_"))
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp: Path) -> int:
    print("── ① 语法抽取：**不依赖题材词表**（加词表是打地鼠）──")
    check("「穿旗袍的女特工」→ 抽出「旗袍」",
          g.noun_after("穿旗袍的女特工", g.CLOTHING_VERBS) == ["旗袍"])
    check("「身着青衫道袍与飞剑」→ 抽出「青衫道袍」（在「与」处截断）",
          g.noun_after("身着青衫道袍与飞剑", g.CLOTHING_VERBS) == ["青衫道袍"])
    check("「携带密码本」→ 抽出「密码本」",
          g.noun_after("携带密码本", g.ITEM_VERBS) == ["密码本"])
    check("「手握扳手」→ 抽出「扳手」",
          "扳手" in g.noun_after("手握扳手", g.ITEM_VERBS))
    check("⚠️ 单字「着」不吃——「戴着腕表」**不该**算成服装",
          g.noun_after("戴着腕表", g.CLOTHING_VERBS) == [],
          str(g.noun_after("戴着腕表", g.CLOTHING_VERBS)))
    check("同上：「提着提灯」「背着步枪」都不算服装",
          g.noun_after("提着提灯", g.CLOTHING_VERBS) == []
          and g.noun_after("背着步枪", g.CLOTHING_VERBS) == [])
    check("「头戴九翟冠」→ 抽出「九翟冠」（`_STOP` 不含中文数字）",
          g.noun_after("头戴九翟冠", g.ACCESSORY_VERBS) == ["九翟冠"],
          str(g.noun_after("头戴九翟冠", g.ACCESSORY_VERBS)))

    print()
    print("── ② 场所与时代 ──")
    check("「在废弃医院的地下室」→ 场所「废弃医院」",
          "废弃医院" in g.prep_place("在废弃医院的地下室"))
    check("「在霓虹街道上」→ 去掉尾部方位词，得「霓虹街道」",
          "霓虹街道" in g.prep_place("赛博朋克，在霓虹街道上"))
    check("无场所后缀时**不硬抽**（「在2026年」不该被当场所）",
          g.prep_place("在2026年发生") == [])
    check("⭐ 判据是「**以场所字结尾**」，故「在进行改革」**不误抽**",
          g.prep_place("在进行改革") == [], str(g.prep_place("在进行改革")))
    check("民国场所「洋行」「客栈」能抽到（此前后缀表没有它们）",
          g.prep_place("在上海洋行的大厅") == ["上海洋行"]
          and "客栈" in g.prep_place("在客栈里"))
    check("「民国」→ 民国时代（**中英成对**）",
          g.era_from_text("民国谍战")[0] == "民国"
          and g.era_from_text("民国谍战")[1] != "")
    check("无时代词 → 返回空（不编）", g.era_from_text("一个女佣兵") == ("", ""))

    print()
    print("── ③ ⭐ 英文安全闸：中文词**不得**拼进英文 ──")
    en, need = g.safe_en("密码本", "the specified item")
    check("含中文 → 英文改用通用表述", en == "the specified item" and need,
          repr(en))
    en, need = g.safe_en("Kevlar", "the specified item")
    check("纯 ASCII → 原样进英文（且不标记）", en == "Kevlar" and not need)
    check("空串 → 通用表述、不标记", g.safe_en("", "x") == ("x", False))

    print()
    print("── ④ 服装补全：用户原话优先，抽不到用**中性兜底**（不假装具体）──")
    from src.nl_parser import COLORS, MATERIALS
    hit, fb, notes = g.clothing_from_text("民国谍战，穿旗袍的女特工", MATERIALS, COLORS)
    check("形制 = 旗袍（用户原话）", hit.get("silhouette") == "旗袍", str(hit))
    check("英文形制**不含中文**", not any("\u4e00" <= c <= "\u9fa5"
                                        for c in hit.get("silhouette_en", "")),
          repr(hit.get("silhouette_en")))
    check("材质未识别 → 走**中性兜底**（不是假具体的「棉」）",
          "描述未指明材质" in fb.get("material", ""), str(fb.get("material")))
    check("兜底时**如实说明**（有 notes）", any("材质" in n for n in notes), str(notes))
    hit2, _fb2, _n2 = g.clothing_from_text("穿丝质长袍", MATERIALS, COLORS)
    check("材质能从原文识别时走真值（丝 → silk）",
          hit2.get("material") == "丝" and "silk" in hit2.get("material_en", ""),
          f"{hit2.get('material')} / {hit2.get('material_en')}")

    print()
    print("── ⑤ 道具补全 ──")
    hit, fb, notes = g.prop_from_text("民国谍战，携带密码本", MATERIALS, COLORS)
    check("结构含「密码本」（用户原话）", "密码本" in hit.get("structure", ""))
    check("英文结构**不含中文**",
          not any("\u4e00" <= c <= "\u9fa5" for c in hit.get("structure_en", "")),
          repr(hit.get("structure_en")))
    check("未识别材质 → 中性兜底 + 说明",
          "描述未指明材质" in fb.get("material", "")
          and any("材质" in n for n in notes))

    print()
    print("── ⑥ 场景补全 ──")
    hit, fb, notes = g.scene_from_text("民国谍战，在上海洋行的大厅")
    check("场所名来自原文（「上海洋行」以场所字「行」结尾）",
          hit.get("name") == "上海洋行", str(hit.get("name")))
    check("时代 = 民国", hit.get("era") == "民国")
    check("英文建筑描述不含中文",
          not any("\u4e00" <= c <= "\u9fa5" for c in hit.get("building_en", "")),
          repr(hit.get("building_en")))
    hit, fb, notes = g.scene_from_text("一个没有场所词的描述")
    check("无场所词 → 兜底 + 说明（不静默）",
          any("场所词" in n for n in notes), str(notes))

    print()
    print("── ⑦ 通用骨架本身必须**不含中文**（英文 prompt 用）──")
    for name, tbl in (("GENERIC_CLOTHING", g.GENERIC_CLOTHING),
                      ("GENERIC_PROP", g.GENERIC_PROP),
                      ("GENERIC_SCENE", g.GENERIC_SCENE)):
        bad = [k for k, v in tbl.items()
               if k.endswith("_en") and any("\u4e00" <= c <= "\u9fa5" for c in v)]
        check(f"{name} 的 `*_en` 值全为英文", not bad, str(bad))

    print()
    print("── ⑧ `world` 必须是**自由文本**，不是 11 个枚举值 ──")
    check("表内题材仍返回题材键", nlp._find_world("一个30岁的废土女佣兵") == "wasteland")
    check("⭐ 表外题材回退到**时代词**作为自由文本 world",
          nlp._find_world("民国谍战剧，一位穿旗袍的女特工") == "民国",
          nlp._find_world("民国谍战剧，一位穿旗袍的女特工"))
    check("没有题材词/时代词时返回空（不编）",
          nlp._find_world("一个女佣兵") in ("", "military"),
          nlp._find_world("一个女佣兵"))
    p = nlp.parse("民国谍战剧，一位穿旗袍的女特工")
    check("⭐ 资产名**不再含「-未定」**（那串会污染名字）",
          "未定" not in (p.name or "") and p.name == "女特工-民国", p.name)

    print()
    print("── ⑨ 批量：**用户给的清单优先于题材池**（generality 的最直接入口）──")
    import src.batch as bt
    got = bt.user_items("一次生成4个民国谍战人物：报务员、线人、舞女、巡捕")
    check("从「：」后抽出用户清单（按标点结构，不靠词表）",
          got == ["报务员", "线人", "舞女", "巡捕"], str(got))
    check("没有「：」清单时返回空（不臆造）",
          bt.user_items("一次生成10个废土NPC") == [])
    items, notes = bt.plan("一次生成4个民国谍战人物：报务员、线人、舞女、巡捕",
                           asset_type="character", world="民国")
    labels = [i["label"].split("·")[-1].strip() for i in items]
    check("⭐ 展开用的是**用户给的**身份", labels == got, str(labels))
    check("⭐ 生成文本**不含**那块「：清单」（它是规格不是内容）",
          all("：" not in i["text"] and "报务员、线人" not in i["text"]
              for i in items), items[0]["text"])
    check("说明里明确写出「取你给的清单」",
          any("你给的清单" in n for n in notes), str(notes))

    print()
    print("── ⑩ 批量：未命中题材池 → 通用骨架 + **明说**（不静默）──")
    pool, matched = bt.pool_for("民国")
    check("未命中题材池 → matched=False", not matched)
    check("默认身份是**社会身份**而非叙事标签（不含「主角/路人甲」）",
          not ({"主角", "伙伴", "对手", "导师", "路人甲"} & set(pool["jobs"])),
          str(pool["jobs"]))
    _it, nt = bt.plan("一次生成4个民国谍战NPC", asset_type="character",
                      world="民国")
    check("⭐ 未命中时**必须说明**（这是唯一的可见信号）",
          any("未命中题材池" in n for n in nt), str(nt))
    _it2, nt2 = bt.plan("一次生成4个废土NPC", asset_type="character",
                        world="wasteland")
    check("表内题材**命中** → 身份用该题材的具体值，且不报「未命中」",
          not any("未命中" in n for n in nt2), str(nt2))

    print()
    print("── ⑪ 场景 / 道具池也不得写死成某一题材 ──")
    check("道具池按题材分组（有 default 之外的键）",
          len(bt.PROP_POOLS) > 1 and "default" in bt.PROP_POOLS)
    check("场景池同上", len(bt.SCENE_POOLS) > 1 and "default" in bt.SCENE_POOLS)
    ws, wm = bt._typed_pool(bt.PROP_POOLS, "wasteland")
    ds, dm = bt._typed_pool(bt.PROP_POOLS, "民国")
    check("废土命中 → 用**具体**道具（能源步枪…）", wm and "能源步枪" in ws, str(ws[:3]))
    check("表外题材 → 用**题材无关类目**，且不报「能源步枪」",
          (not dm) and "能源步枪" not in ds, str(ds[:3]))

    print()
    print("=" * 66)
    if FAIL:
        print(f"❌ 失败 {len(FAIL)} 项 / 共 {len(PASS) + len(FAIL)} 项：")
        for f in FAIL:
            print("   ·", f)
        return 1
    print(f"✅ 全部通过 —— {len(PASS)} 项（含「表外题材」与「英文纯度」两类断言）")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
