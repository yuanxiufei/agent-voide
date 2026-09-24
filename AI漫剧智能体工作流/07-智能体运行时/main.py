#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI漫剧资产库 Agent · 命令行入口。

═══════════════════════════════════════════════════════════════════
最快上手
═══════════════════════════════════════════════════════════════════
    python main.py "一个30岁的废土女佣兵，机械左臂，穿旧军用风衣"
    python main.py "把她的头发换成银白色"
    python main.py list
    python main.py show CHR_001
    python main.py doctor

**无需任何 API Key 即可跑通全流程**（规则解析 + mock 出图）。
配置 `MODEL_API_KEY` / `IMAGE_API_KEY` 后自动升级为真实模型。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src import batch, dispatcher, handover, module_loader, registry  # noqa: E402
from src.agent import AgentConfig, DramaAssetAgent            # noqa: E402
from src.consistency import check_required, check_text_risk   # noqa: E402
from src.module_loader import ModuleLoader                    # noqa: E402
from src.prompt_engine import build_source_prompt             # noqa: E402
from src.runtime import Runtime                               # noqa: E402

ROOT = Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────────
# 输出辅助
# ─────────────────────────────────────────────────────────────

def hr(title: str = "") -> None:
    print("\n" + "─" * 66)
    if title:
        print(title)
        print("─" * 66)


def print_report(rep, title: str = "一致性 Gate") -> None:
    hr(f"🧪 {title}：{rep.summary()}")
    for i in rep.issues:
        icon = {"error": "❌", "warn": "⚠️", "info": "ℹ️"}.get(i.level, "·")
        print(f"  {icon} [{i.code}] {i.message}")
        if i.expected or i.actual:
            print(f"      期望：{i.expected or '(空)'}")
            print(f"      实际：{i.actual or '(空)'}")
    if not rep.issues:
        print("  ✅ 无问题")


def print_asset(card) -> None:
    hr(f"🎨 {card.id} ｜ {card.name} ｜ {card.type} ｜ {card.version}"
       f" ｜ {card.id_status}")
    print(f"  世界观：{card.world or '—'}   身份：{card.occupation or '—'}"
          f"   年龄：{card.age or '—'}   性别：{card.gender or '—'}")
    print(f"  指纹  ：{card.fingerprint()}（固定特征锁定，派生卡必须一致）")
    vd = card.visual_dna
    for label, val in (("面部", [vd.face_shape, vd.jaw, vd.brow_ridge, vd.lips]),
                       ("眼睛", [vd.eye_shape, vd.eye_color]),
                       ("发型", [vd.hair_length, vd.hair_style, vd.hair_color]),
                       ("体型", [vd.height, vd.body_type]),
                       ("服装", [vd.layers]),
                       ("材质", [vd.material, vd.surface_texture]),
                       ("装备", [vd.signature_accessory]),
                       ("配色", [vd.primary_color])):
        v = " · ".join(x for x in val if x)
        if v:
            print(f"  {label}  ：{v[:88]}")


# ─────────────────────────────────────────────────────────────
# 子命令
# ─────────────────────────────────────────────────────────────

def cmd_ask(a: argparse.Namespace) -> int:
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    text = " ".join(a.text).strip()
    if not text:
        print("请给出描述，例如：python main.py \"一个废土女佣兵\"")
        return 2
    if a.no_image:
        ag.cfg.generate = False
    if a.provider:
        ag.cfg.provider = a.provider
    if a.reference:
        ag.cfg.reference_image = a.reference
    if a.type:
        ag.cfg.provider = ag.cfg.provider  # 类型由 route 层处理

    hr("🧭 路由")
    res = ag.handle(text, asset_type=a.type, generate=(not a.no_image))
    r = res.get("route", {})
    print(f"  意图：{r.get('operation')}   资产类型：{r.get('asset_type')}"
          f"   解析器：{res.get('parser', r.get('source'))}")
    print(f"  依据：{r.get('reason')}")

    if res.get("operation") == "query":
        hr(f"📚 查询结果：{res['count']} 项")
        for it in res["items"]:
            print(f"  {it['id']}  {it['name']}  [{it['type']}]  {it['world']}"
                  f"  {it['version']}  {it['status']}")
        return 0

    if not res.get("ok", True):
        print(f"\n❌ {res.get('error')}")
        return 1

    hr("🧩 补全说明")
    for n in res.get("notes", []):
        print(f"  · {n}")

    from src.schema import AssetCard
    card = AssetCard.from_dict(res["card"])
    print_asset(card)
    if res.get("from_version"):
        print(f"\n  版本：{res['from_version']} → {res['version']}（原版本保留）")
    if res.get("changes"):
        hr("✏️ 本次改动")
        for k, v in res["changes"].items():
            print(f"  · {k} = {v}")

    hr("🇬🇧 English Prompt (MASTER)")
    print(res["prompt_en"])
    hr("🇨🇳 中文提示词")
    print(res["prompt_cn"])
    hr("🚫 Negative Prompt（来源：工作流 NEGATIVE-PROMPT-LIBRARY + TURNAROUND §1.6）")
    neg = res["negative"]
    # 完整打印：末尾的「文字屏蔽强制段」（含权重 `any text:1.8`）是关键约束，
    # 截断会让人以为它不存在（实测踩到：只显示前 600 字符时看不到权重标记）。
    print(neg)
    print(f"\n  （共 {len(neg.split(','))} 条；含权重标记 any text:1.8："
          f"{'✅' if 'any text:1.8' in neg else '❌ 缺失'}）")

    if res.get("images"):
        hr("🖼️ 产出图像")
        for p in res["images"]:
            size = os.path.getsize(p) if os.path.exists(p) else 0
            print(f"  {p}  ({size / 1024:.1f} KB)")

    print_report(res["consistency"], "一致性 Gate")

    hr("📦 落盘")
    for k, v in (res.get("files") or {}).items():
        print(f"  {k:9s} {v}")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    cards = ag.am.list_assets(asset_type=a.type or "", world=a.world or "",
                              keyword=a.keyword or "")
    hr(f"📚 资产库：{len(cards)} 项")
    if not cards:
        print("  （空）用 `python main.py \"一个废土女佣兵\"` 建第一个")
    for c in cards:
        print(f"  {c.id:10s} {c.type:10s} {c.version:6s} {c.id_status:10s} "
              f"{(c.name or '')[:24]:24s} {c.world}")
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    aid = ag.am.resolve_id(a.asset_id)
    card = ag.am.load(aid, a.version or "latest")
    if not card:
        print(f"❌ 找不到 {aid}")
        return 1
    print_asset(card)
    hist = ag.am.history(aid)
    print(f"\n  版本历史：{' → '.join(hist) if hist else '（无）'}")
    rep = check_required(card, ag.rules)
    rep.issues.extend(check_text_risk(card.prompt_en, card.negative_prompt).issues)
    print_report(rep)
    return 0


def cmd_rules(a: argparse.Namespace) -> int:
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    s = ag.rules.summary()
    hr("📖 权威规则来源（**只读**工作流，本项目不复制）")
    print(f"  运行模式  ：{s['mode']}（live=实时读取工作流）")
    print(f"  工作流根  ：{s['workflow_root']}")
    print(f"  快照目录  ：{s['vendor_dir']}")
    print(f"  通用负面词：{s['negative_common']} 条")
    print(f"  三视图负面：{s['negative_three_view']} 条")
    print(f"  按模块追加：{'、'.join(s['negative_modules'])}")
    print(f"  修复映射  ：{'、'.join(s['failure_rules'])}")
    print(f"  质量参数  ：{'、'.join(s['quality_params'])}")
    print(f"  服装字段  ：{s['costume_fields']} 项")
    print(f"  道具字段  ：{s['prop_fields']} 项")
    print(f"  ID 前缀   ：{s['id_prefixes']}")
    hr("三视图硬标准（§1.1 表）")
    for k, v in ag.rules.turnaround_standard.items():
        print(f"  {k}：{v}")
    hr("文字屏蔽强制段（§1.6，缺权重 1.8 无效）")
    print(f"  正向：{ag.rules.text_block_positive}")
    print(f"  反向：{ag.rules.text_block_negative}")
    # ⚠️ 覆盖项**必须展示** —— 本机覆盖是静默生效的，不显示就无从解释
    #    「prompt 为什么和上次不一样」（实测踩过同类问题：负面词被截断显示 → 看不见权重标记）
    hr("🧩 本机覆盖层（prompts/overrides/）")
    print(ag.rules.overrides.report())
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    if a.snapshot:
        meta = ag.rules.export()
        hr("📸 已导出规则快照到 vendor/（供不含工作流目录的机器使用）")
        print(f"  来源工作流：{meta['workflow_root']}")
        print(f"  记录 hash ：{len(meta['hashes'])} 个文件")
        for k, v in meta["hashes"].items():
            print(f"    {v}  {k}")
        return 0
    out = a.out or str(ROOT / "assets_export.zip")
    ag.am.export(out)
    hr("📦 已导出资产 ZIP（蓝图 §十九：用于跨电脑迁移）")
    print(f"  {out}  ({os.path.getsize(out) / 1024:.1f} KB)")
    return 0


def cmd_doctor(a: argparse.Namespace) -> int:
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    d = ag.doctor()
    hr("🩺 环境自检")
    print(f"  项目根    ：{d['root']}")
    print(f"  规则源    ：{d['rules']['mode']}  ← {d['rules']['workflow_root']}")
    snap = d["snapshot"]
    print(f"  快照      ：{'✅ 一致' if snap['ok'] else '⚠️ ' + snap['detail']}")
    print(f"  LLM       ：{d['llm']}")
    print(f"  当前 Provider：{d['active_provider']}")
    print(f"  资产总数  ：{d['asset_count']}")
    hr("可用 Provider")
    for p in d["providers"]:
        icon = "✅" if p["available"] else "⛔"
        print(f"  {icon} {p['name']:10s} {p['reason']}")
    hr("🧩 本机覆盖层（prompts/overrides/）")
    print(ag.rules.overrides.report())
    hr("输图后人工复核清单（RULE-005 要求逐字检查隐蔽位置）")
    for x in d["text_risk_checklist"]:
        print(f"  □ {x}")
    return 0


def cmd_probe(a: argparse.Namespace) -> int:
    """只跑 Prompt，不出图 —— 用于快速核对提示词质量。"""
    a.no_image = True
    return cmd_ask(a)


def _apply_gen_args(ag, a: argparse.Namespace) -> None:
    """把出图相关命令行参数**真正应用到** agent。

    ⚠️ 抽出来是因为踩过：`panorama` / `angles` / `batch` 三个命令都声明了
    `--provider`，但**没有一个把它传下去** —— 用户以为切了 Provider，
    实际仍是 config 里的 mock，而且**没有任何提示**。
    「参数被接受但静默忽略」是比报错更难查的一类问题（本项目反复强调这点）。
    """
    if getattr(a, "no_image", False):
        ag.cfg.generate = False
    if getattr(a, "provider", None):
        ag.cfg.provider = a.provider
    if getattr(a, "reference", None):
        ag.cfg.reference_image = a.reference


def cmd_panorama(a: argparse.Namespace) -> int:
    """场景 360° 全景空间基准（工作流 §4.6「全景定基准 → 六角度出分镜可用图」）。"""
    text = " ".join(a.text)
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    _apply_gen_args(ag, a)
    hr("🌐 场景 360° 全景基准（§4.6）")
    print(f"  输入：{text}")
    res = ag.panorama(text, generate=(not a.no_image))
    if res.get("error"):
        print(f"  ❌ {res['error']}")
        return 2
    hr(f"🎨 {res['asset_id']} ｜ {res['card']['name']} ｜ {res['version']}")
    for n in res["notes"]:
        print(f"  · {n}")
    print()
    print("  ── English（§4.6 模板 + [场景描述] 已替换）──")
    for line in res["prompt_en"].splitlines():
        if line.startswith(("SCENE:", "LAYOUT:", "MULTI-ANGLE")):
            print("  " + line[:150])
    print()
    print(f"  Negative 条数：{len(res['negative'].split(', '))}"
          f"（含 §4.6 全景反向词：{'✅' if 'perspective distortion' in res['negative'] else '❌'}）")
    print()
    print(f"  📦 {res['files']['card']}")
    return 0


def cmd_drift(a: argparse.Namespace) -> int:
    """§六「漂移检测」：交付物引用的 ID 是否都在总表里、有没有自造 ID。

    这是 §六 里那句「每当有模块交付，检查其引用的 ID 是否都在 ID 总表中」
    的**确定性实现** —— 原本它只是被原样粘进 System Prompt。
    """
    from src import drift
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    known, gap = drift.load_registry(ag.cfg.root)

    if a.file:
        p = Path(a.file)
        if not p.is_file():
            print(f"❌ 文件不存在：{a.file}")
            return 2
        hr(f"🧭 漂移检测 · 交付物 {a.file}")
        rep = drift.check_text(p.read_text(encoding="utf-8"), known,
                               scope=str(a.file))
        rep.registry_gap = []
    else:
        hr("🧭 漂移检测 · 全库（§六 全局一致性守护）")
        rep = drift.scan_output(ag.cfg.root, known)
        rep.registry_gap = gap

    rep.type_conflict = drift.check_conflicts(ag.cfg.root)
    rep.unchecked = list(drift.UNCHECKED_NOTES)
    print(rep.render())
    return 0 if rep.ok else 1


def cmd_verify(a: argparse.Namespace) -> int:
    """核验产出实物（卡 / 提示词 / 图 / 索引表）。"""
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    hr(f"🔍 产出核验 · {a.asset_id}")
    r = ag.verify(a.asset_id)
    if not r.get("checks") and r.get("error"):
        print(f"  ❌ {r['error']}")
        return 2
    for c in r["checks"]:
        icon = {True: "✅", False: "❌", None: "ℹ️"}.get(c["ok"], "·")
        print(f"  {icon} {c['name']}：{c['detail']}")
    hr("⚠️ 本命令**未**核验的项（不要以为 verify 通过 = 一切都对）")
    for u in r.get("unchecked", []):
        print(f"  □ {u}")
    print()
    print(f"  结论：{'✅ 客观项全部通过' if r['ok'] else '❌ 有客观项未通过'}")
    return 0 if r["ok"] else 1


def cmd_angles(a: argparse.Namespace) -> int:
    """场景 S01–S06 六角度 + 场景资产库索引表（INDEX-TEMPLATES §4.1）。"""
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    _apply_gen_args(ag, a)
    hr(f"🎬 场景多角度（§4.1）· {a.env_id}")
    res = ag.angles(a.env_id, generate=(not a.no_image),
                    reference=a.reference or "")
    if not res.get("ok"):
        print(f"  ❌ {res.get('error')}")
        return 2
    for n in res["notes"]:
        print(f"  · {n}")
    print()
    hr("📋 场景资产库索引表（§4.1 要求**必须建**）")
    print(res["index_table"])
    print()
    if a.verbose:
        for it in res["items"]:
            hr(f"{it['no']} · {it['shot']}")
            print(it["prompt_en"])
    hr("📦 落盘")
    for k, v in res["files"].items():
        print(f"  {k:6s} {v}")
    return 0


def cmd_batch(a: argparse.Namespace) -> int:
    """批量生成（蓝图 §十八：一次生成 10 个废土 NPC）。"""
    text = " ".join(a.text)
    ag = DramaAssetAgent(AgentConfig.load(ROOT))
    _apply_gen_args(ag, a)
    count = a.count or batch.parse_count(text)
    hr(f"📦 批量生成：{count} 项")
    print(f"  请求：{text}")
    print(f"  展开为 {count} 条独立请求，各自走正常创建流程"
          f"（同 Gate / 指纹 / 版本 / 落盘）")
    print()
    # ⚠️ 预览必须用 `ag.plan_batch()`（会带上世界观）—— 直接 `batch.plan()`
    #    会落到通用池，于是「预览是主角/伙伴、实际是拾荒者」两边不一致（实测踩到）
    _t, preview = ag.plan_batch(text, count=count, asset_type=a.type or "")
    for it in preview:
        print(f"  {it['index']:>2}. {it['label']:<22s} {it['text']}")
    print()
    res = ag.batch(text, count=count, asset_type=a.type or "",
                   generate=(not a.no_image))
    hr("📋 花名册")
    print(res["roster"])
    if a.verbose:
        hr("逐项一致性")
        for it in res["items"]:
            flag = "✅" if it["ok"] else "❌"
            print(f"  {flag} {it['asset_id'] or '—':<26s} {it['consistency'] or it['error']}")
    return 0


# ─────────────────────────────────────────────────────────────
# 七个流程 agent（通用运行时的命令）
# ─────────────────────────────────────────────────────────────

def _agent(name: str):
    spec = registry.resolve(name)
    if spec is None:
        print(f"❌ 未找到 agent「{name}」。可用："
              f"{' / '.join(s.key + '(' + s.no + ')' for s in registry.REGISTRY)}")
    return spec


def cmd_agents(a: argparse.Namespace) -> int:
    """列出全部流程 agent（由注册表生成，不会与实现失联）。"""
    loader = ModuleLoader()
    hr("🧩 流程 agent 一览（**每个模块都可独立运行**）")
    print(f"  工作流根：{loader.root or '⚠️ 未找到'}\n")
    for s in registry.REGISTRY:
        miss = loader.missing(s)
        flag = "" if not miss else f"  ⚠️ 缺 {len(miss)} 份文档"
        print(f"  【{s.no}】{s.name:<12s} key={s.key:<13s}{flag}")
        print(f"        职责：{s.summary}")
        print(f"        交付：{' · '.join(s.outputs) or '—'}")
        if s.gate:
            print(f"        门禁：{s.gate}（"
                  f"{' / '.join(c.label for c in s.gate_checks)}）")
        print(f"        启动：python main.py init {s.key}")
        print()
    print("  通用命令：run / init / route / handover / gate / doc / outline")
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    """用**任意** agent 处理输入（有 Key 真调模型；无 Key 出可粘贴调用包）。"""
    spec = _agent(a.agent)
    if not spec:
        return 2
    text = " ".join(a.text)
    rt = Runtime()
    hr(f"🤖 {spec.no} {spec.name}  ← {spec.key}")
    print(f"  工作流根：{rt.loader.root or '⚠️ 未找到'}")
    res = rt.run(spec, text, brief=a.brief)
    hr(f"模式：{'LLM 真实调用' if res.mode == 'llm' else '调用包（未配 Key）'}")
    for n in res.notes:
        print(f"  ℹ️ {n}")
    if res.answer:
        print()
        print(res.answer)
    else:
        hr("📋 可直接粘贴的调用包（System + User）")
        print(res.call_package)
    if res.saved:
        hr("📦 落盘")
        for k, v in res.saved.items():
            print(f"  {k:6s} {v}")
    return 0


def cmd_init(a: argparse.Namespace) -> int:
    """输出某个 agent 的「初始化指令」—— 独立启动它时该说的开场白。"""
    spec = _agent(a.agent)
    if not spec:
        return 2
    rt = Runtime()
    hr(f"🚀 独立启动：{spec.no} {spec.name}")
    print(rt.greet(spec))
    print()
    print(f"  接着可用：python main.py run {spec.key} \"<你的输入>\"")
    return 0


def cmd_route(a: argparse.Namespace) -> int:
    """00 总控路由：判定输入该进哪个 agent。"""
    text = " ".join(a.text)
    r = dispatcher.route(text)
    hr("🧭 路由判定")
    print(f"  输入：{text}")
    print(f"  结论：{'✅ ' if r.confident else '⚠️ '}{r.agent.no} {r.agent.name}"
          if r.agent else "  结论：无法判定")
    print(f"  依据：{r.reason}")
    if r.scores:
        print(f"  得分：{' · '.join(f'{k}={v}' for k, v in r.scores.items())}")
    if not r.confident:
        print()
        print(f"  ❓ 按工作流 §八·5「不确定就问一句」，先问：{r.question}")
        if r.candidates:
            print(f"     候选：{' / '.join(r.candidates)}")
    print()
    print(f"  推进：python main.py run {r.agent.key} \"{text}\"")
    return 0


def cmd_handover(a: argparse.Namespace) -> int:
    """生成某模块的「交接清单」骨架；给了文件则做校验。"""
    spec = _agent(a.agent)
    if not spec:
        return 2
    hr(f"📤 交接清单 · {spec.no} {spec.name}")
    print(handover.skeleton(spec))
    if a.file:
        p = Path(a.file)
        if not p.is_file():
            print(f"\n❌ 文件不存在：{a.file}")
            return 2
        txt = p.read_text(encoding="utf-8")
        print()
        print(f"  校验 {a.file}：")
        print(handover.check_handover(txt, spec).render())
    return 0


def cmd_gate(a: argparse.Namespace) -> int:
    """门禁预检：给定交付物文本（或文件），按该模块门禁标准检查。"""
    if a.agent == "all":
        hr("🚪 三门禁一览")
        print(handover.gate_overview())
        return 0
    spec = _agent(a.agent)
    if not spec:
        return 2
    if not a.file:
        hr(f"🚪 门禁「{spec.gate or '（本模块无门禁）'}」· {spec.name}")
        for c in spec.gate_checks:
            print(f"  □ {c.label}")
            print(f"      判据（命中任一即算检出）：{' / '.join(c.any_of)}")
        print(f"  判定：python main.py gate {spec.key} <交付物文件>")
        return 0
    p = Path(a.file)
    if not p.is_file():
        print(f"❌ 文件不存在：{a.file}")
        return 2
    hr(f"🚪 门禁预检 · {spec.gate or spec.name}")
    print(handover.check_gate(p.read_text(encoding="utf-8"), spec).render())
    return 0


def cmd_doc(a: argparse.Namespace) -> int:
    """查看工作流里任意文档（或它的某一节）—— 供 agent 按需取原文。"""
    loader = ModuleLoader()
    t = loader.text(a.path)
    if not t:
        print(f"❌ 未找到：{a.path}")
        print("  提示：路径相对工作流根，如 `02-服化道/引擎/TURNAROUND-STANDARD.md`")
        return 2
    if a.section:
        # level=None：**任意级别**都找 —— 用户会说「取 1.6 节」，而 1.6 是 `###` 级
        s = module_loader.section(t, a.section, level=None)
        if not s:
            print(f"❌ 该文档里没有含「{a.section}」的章节。可用章节：\n")
            print(module_loader.outline(t))
            return 2
        print(s)
        return 0
    print(t)
    return 0


def cmd_outline(a: argparse.Namespace) -> int:
    """列出工作流里有哪些文档（按模块分组）—— 通用检索入口。"""
    loader = ModuleLoader()
    if not loader.root:
        print("❌ 未找到工作流目录")
        return 2
    hr("🗂 工作流文档清单（agent 的全部可读素材）")
    for s in registry.REGISTRY:
        docs = s.role_docs + s.ref_docs
        if not docs:
            continue
        print(f"\n  【{s.no}】{s.name}")
        for d in docs:
            ok = "✅" if loader.exists(d) else "❌"
            print(f"    {ok} {d}")
    return 0


# ─────────────────────────────────────────────────────────────
# 参数
# ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="AI漫剧资产库Agent",
        description="把一句话变成可复用的 AI 漫剧视觉资产（中英提示词 + 资产卡 + 图像）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python main.py \"一个30岁的废土女佣兵，机械左臂，穿旧军用风衣\"\n"
               "  python main.py \"把她的头发换成银白色\"\n"
               "  python main.py probe \"赛博朋克女医生，义眼\"   # 只出提示词\n"
               "  python main.py rules                          # 看加载了哪些权威规则\n")
    sub = p.add_subparsers(dest="cmd")

    def add_gen_args(sp):
        sp.add_argument("--no-image", action="store_true", help="只出提示词，不出图")
        sp.add_argument("--provider", choices=["mock", "openai", "stability"],
                        help="覆盖 config.json 的图像 Provider")
        sp.add_argument("--type", choices=["character", "costume", "prop", "environment"],
                        help="强制资产类型（不自动判定）")
        sp.add_argument("--reference", metavar="图路径",
                        help="挂一张参考图做**图生图**（保形象/空间一致）。"
                             "openai → /images/edits · stability → mode=image-to-image")

    q = sub.add_parser("ask", help="一句话创建/修改资产")
    q.add_argument("text", nargs="+")
    add_gen_args(q)

    pr = sub.add_parser("probe", help="只生成 Prompt，不出图")
    pr.add_argument("text", nargs="+")
    add_gen_args(pr)

    pa = sub.add_parser("panorama", help="场景 360° 全景空间基准（§4.6）")
    pa.add_argument("text", nargs="+", help="场景描述，或已有 ENV_00X（派生全景基准卡）")
    pa.add_argument("--no-image", action="store_true")
    pa.add_argument("--provider", choices=["mock", "openai", "stability"])

    vf = sub.add_parser("verify", help="核验产出实物（卡 / 提示词 / 图 / 索引表）")
    vf.add_argument("asset_id")

    df = sub.add_parser("drift", help="§六 漂移检测：引用的 ID 在不在总表里")
    df.add_argument("file", nargs="?", help="要检查的交付物文件；省略则扫全库 output/")

    ag_ = sub.add_parser("angles", help="场景 S01–S06 六角度 + 索引表（§4.1）")
    ag_.add_argument("env_id", help="场景 ID，如 ENV_001")
    ag_.add_argument("-v", "--verbose", action="store_true", help="逐角度打印提示词")
    ag_.add_argument("--no-image", action="store_true")
    ag_.add_argument("--provider", choices=["mock", "openai", "stability"])
    ag_.add_argument("--reference", metavar="图路径",
                     help="S02–S06 的基图（通常不必给 —— 默认自动用 S01 的出图）；"
                          "⚠️ S01 **永远**是纯文字生成，不受此参数影响（§4.1 铁则①）")

    ba = sub.add_parser("batch", help="批量生成（蓝图 §十八：一次 10 个 NPC）")
    ba.add_argument("text", nargs="+")
    ba.add_argument("--count", type=int, default=0, help="数量（默认从输入里的「N个」取，否则 10）")
    ba.add_argument("-v", "--verbose", action="store_true", help="逐项打印一致性")
    add_gen_args(ba)

    ls = sub.add_parser("list", help="列出资产库")
    ls.add_argument("--type", choices=["character", "costume", "prop", "environment"])
    ls.add_argument("--world", help="按世界观过滤，如 wasteland")
    ls.add_argument("--keyword", help="按关键词过滤")

    sh = sub.add_parser("show", help="查看某个资产")
    sh.add_argument("asset_id")
    sh.add_argument("--version", help="默认 latest")

    sub.add_parser("rules", help="显示从工作流加载的权威规则")

    ex = sub.add_parser("export", help="导出资产 ZIP 或规则快照")
    ex.add_argument("--out", help="ZIP 输出路径")
    ex.add_argument("--snapshot", action="store_true", help="导出规则快照到 vendor/")

    sub.add_parser("doctor", help="环境自检")

    # ── 七个流程 agent（通用运行时）──
    sub.add_parser("agents", help="列出全部流程 agent（00-06）")
    sub.add_parser("outline", help="列出工作流文档清单（按模块）")

    ru = sub.add_parser("run", help="用任意 agent 处理输入")
    ru.add_argument("agent", help="agent：orchestrator/script/asset/storyboard/video/audio/compliance（或编号 00-06）")
    ru.add_argument("text", nargs="+")
    ru.add_argument("--brief", action="store_true",
                    help="角色文档只给目录（省 token，用于快速核对结构）")

    ini = sub.add_parser("init", help="输出某 agent 的初始化指令（独立启动）")
    ini.add_argument("agent")

    rt = sub.add_parser("route", help="00 总控路由：判定输入该进哪个 agent")
    rt.add_argument("text", nargs="+")

    ho = sub.add_parser("handover", help="生成/校验某模块的交接清单")
    ho.add_argument("agent")
    ho.add_argument("--file", help="给了则做字段校验")

    ga = sub.add_parser("gate", help="门禁预检")
    ga.add_argument("agent", help="agent 名，或 all 看三门禁一览")
    ga.add_argument("file", nargs="?", help="交付物文件；省略则只打印标准")

    dc = sub.add_parser("doc", help="查看工作流任意文档（或某一节）")
    dc.add_argument("path", help="相对工作流根的路径")
    dc.add_argument("--section", help="只取含该关键词的章节")

    return p


def main() -> int:
    argv = sys.argv[1:]
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    # 无子命令时默认走 ask（支持 `python main.py "一个废土女佣兵"` 的直白用法）
    if argv[0] not in ("ask", "probe", "batch", "panorama", "angles", "verify",
                       "drift", "list", "show", "rules", "export", "doctor",
                       "agents", "outline", "run", "init", "route", "handover",
                       "gate", "doc", "-h", "--help"):
        argv = ["ask"] + argv
    a = parser.parse_args(argv)
    fn = {"ask": cmd_ask, "probe": cmd_probe, "batch": cmd_batch,
          "panorama": cmd_panorama, "angles": cmd_angles, "verify": cmd_verify,
          "drift": cmd_drift, "list": cmd_list, "show": cmd_show,
          "rules": cmd_rules, "export": cmd_export, "doctor": cmd_doctor,
          "agents": cmd_agents, "outline": cmd_outline, "run": cmd_run,
          "init": cmd_init, "route": cmd_route, "handover": cmd_handover,
          "gate": cmd_gate, "doc": cmd_doc}
    if not a.cmd:
        parser.print_help()
        return 0
    return fn[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
