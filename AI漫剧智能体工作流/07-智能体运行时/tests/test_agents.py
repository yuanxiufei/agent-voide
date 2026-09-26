# -*- coding: utf-8 -*-
"""**项目级子智能体**测试（`.codebuddy/agents/manju-*.md`）。

═══════════════════════════════════════════════════════════════════
为什么 07 的测试要管仓库根的 agent 配置
═══════════════════════════════════════════════════════════════════
那 7 个 `.codebuddy/agents/manju-*.md` 是**本仓库的交付物** ——
它们告诉 CodeBuddy「AI漫剧工作流的 7 个流程 agent 怎么用这个仓库」。
它们和 07 的关系是：**规则只读工作流、确定性步骤调 07 的代码**。
所以校验它们"引用的路径与命令是否真实"是 07 的职责边界内的事。

═══════════════════════════════════════════════════════════════════
三类问题（都是"看起来对但实际错"）
═══════════════════════════════════════════════════════════════════
① **frontmatter 能否被 YAML 解析** —— 描述里的冒号/引号最容易破坏它，
   而且是**静默**的（agent 加载失败或字段被截断，你不会立刻知道）。
② **必填字段齐不齐** —— 官方：`agentic` 模式 `name` 与 `description` 必填。
③ ⭐ **引用的路径是否指向唯一一份** —— 工作流里 `00-主控智能体.md` 有 **5 份**
   （01/02/04/05/06 各一份）。只写文件名会让 agent **读错模块的文档**，
   而那看起来"完全正常"。

⚠️ 检查器也要**被检查**：本文件第一版把 Windows 的 `\` 当成 `/` 做后缀匹配，
于是把 18 条**真实存在**的路径全判成"找不到" —— 差点让我去改对的代码。
（同日在 `tests/test_dict.py` 也踩过"断言自己写错"。）

运行：`python tests/test_agents.py`
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent                       # 07-智能体运行时
WF = RUN.parent                         # AI漫剧智能体工作流
ROOT = WF.parent                        # 仓库根
AG = ROOT / ".codebuddy" / "agents"

sys.path.insert(0, str(RUN))

try:
    import yaml
    HAVE_YAML = True
except Exception:                                          # noqa: BLE001
    HAVE_YAML = False

PASS, FAIL = [], []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(label)
    print(f"  {'OK  ' if ok else '❌  '} {label}"
          + (f"   ← {detail}" if detail and not ok else ""))


def main() -> int:
    print(f"  agent 目录：{AG}")
    if not AG.is_dir():
        check("项目级子智能体目录存在", False, str(AG))
        return 1
    files = sorted(p for p in AG.glob("*.md") if not p.name.startswith("_"))
    check(f"找到 {len(files)} 个子智能体（期望 7 个：00–06）", len(files) == 7, str(len(files)))

    # 工作流全部 .md（判"歧义"用）
    # ⚠️ 统一转 `/` —— Windows 上 `Path` 给 `\`，直接拿 `/` 匹配会**全部落空**
    all_md = [str(p.relative_to(ROOT)).replace("\\", "/") for p in WF.rglob("*.md")]

    help_txt = subprocess.run(
        [sys.executable, "main.py", "-h"], cwd=RUN, capture_output=True,
        text=True, encoding="utf-8", errors="replace").stdout
    m = re.search(r"\{([a-z0-9,\-]+)\}", help_txt)
    cmds = set(m.group(1).split(",")) if m else set()
    check(f"读到 07 的子命令清单（{len(cmds)} 个）", len(cmds) > 10, str(cmds))

    for p in files:
        print()
        print(f"── {p.name} ──")
        t = p.read_text(encoding="utf-8")
        mt = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", t, re.S)
        if not mt:
            check("有 frontmatter 块", False, p.name)
            continue
        fm_txt, body = mt.group(1), mt.group(2)

        if HAVE_YAML:
            try:
                fm = yaml.safe_load(fm_txt) or {}
            except Exception as e:                          # noqa: BLE001
                check("frontmatter 可被 YAML 解析", False, f"{type(e).__name__}: {e}")
                continue
            if not isinstance(fm, dict):
                check("frontmatter 可被 YAML 解析", False, type(fm).__name__)
                continue
        else:
            fm = dict(l.split(":", 1) for l in fm_txt.splitlines()
                      if ":" in l and not l.startswith(" "))  # 退化的兜底解析

        check("有 name", bool(fm.get("name")), str(fm.get("name")))
        check("有 description（agentic 必填）", bool(fm.get("description")))
        d = str(fm.get("description", ""))
        check("description 写了**触发条件**（'当…时使用'）",
              "当" in d and "使用" in d, d[:60])
        check("有 tools 白名单（官方建议：只给所需）", bool(fm.get("tools")))
        check("agentMode ∈ agentic/manual",
              fm.get("agentMode") in ("agentic", "manual"), str(fm.get("agentMode")))
        check("name == 文件名", fm.get("name") == p.stem,
              f"{fm.get('name')} vs {p.stem}")

        # ⭐ 第一纪律必须写进 System Prompt
        check("写明「不改工作流权威文档」", "不改工作流权威文档" in body)
        check("写明「规则只读工作流、不复制」", "只读工作流" in body or "绝不复制" in body)

        # ⭐ 路径：完整路径要存在；简写路径必须**唯一**
        for ref in sorted(set(re.findall(r"`([0-9A-Za-z\u4e00-\u9fff_\-/]+\.md)`", body))):
            if ref.startswith("AI漫剧智能体工作流/"):
                check(f"路径存在: {ref}", (ROOT / ref).is_file())
                continue
            hits = [q for q in all_md if q.endswith("/" + ref) or q == ref]
            if len(hits) == 1:
                check(f"简写路径唯一: {ref}", True)
            elif len(hits) > 1:
                check(f"⚠️ 简写路径**歧义**: {ref}", False,
                      f"命中 {len(hits)} 份（agent 会读错模块）")
            else:
                check(f"路径存在: {ref}", False, "工作流里找不到")

        # ⭐ 命令必须真实存在（写了不存在的命令 = 误导 agent）
        for c in sorted(set(re.findall(r"main\.py\s+([a-z0-9\-]+)", body))):
            check(f"命令存在: main.py {c}", c in cmds)

    print()
    print("=" * 66)
    if FAIL:
        print(f"❌ 失败 {len(FAIL)} 项 / 共 {len(PASS) + len(FAIL)} 项：")
        for f in FAIL:
            print("   ·", f)
        return 1
    print(f"✅ 全部通过 —— {len(PASS)} 项")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
