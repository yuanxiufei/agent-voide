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

from src.agent import AgentConfig, DramaAssetAgent            # noqa: E402
from src.consistency import check_required, check_text_risk   # noqa: E402
from src.prompt_engine import build_source_prompt             # noqa: E402

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
    hr("输图后人工复核清单（RULE-005 要求逐字检查隐蔽位置）")
    for x in d["text_risk_checklist"]:
        print(f"  □ {x}")
    return 0


def cmd_probe(a: argparse.Namespace) -> int:
    """只跑 Prompt，不出图 —— 用于快速核对提示词质量。"""
    a.no_image = True
    return cmd_ask(a)


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

    q = sub.add_parser("ask", help="一句话创建/修改资产")
    q.add_argument("text", nargs="+")
    add_gen_args(q)

    pr = sub.add_parser("probe", help="只生成 Prompt，不出图")
    pr.add_argument("text", nargs="+")
    add_gen_args(pr)

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
    return p


def main() -> int:
    argv = sys.argv[1:]
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    # 无子命令时默认走 ask（支持 `python main.py "一个废土女佣兵"` 的直白用法）
    if argv[0] not in ("ask", "probe", "list", "show", "rules", "export", "doctor",
                       "-h", "--help"):
        argv = ["ask"] + argv
    a = parser.parse_args(argv)
    fn = {"ask": cmd_ask, "probe": cmd_probe, "list": cmd_list, "show": cmd_show,
          "rules": cmd_rules, "export": cmd_export, "doctor": cmd_doctor}
    if not a.cmd:
        parser.print_help()
        return 0
    return fn[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
