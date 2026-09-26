# -*- coding: utf-8 -*-
"""把 `智能体搭建参考md/` 的 6 份智能体规格，**逐字移植**成 CodeBuddy 子智能体。

═══════════════════════════════════════════════════════════════════
为什么是"逐字移植"而不是"改写"
═══════════════════════════════════════════════════════════════════
那 6 份规格**本身就是按 System Prompt 设计的**（它们自己写着
「适用：Custom GPT / Agent / System Prompt / 工作流编排器」）。
所以正确做法是**加一层 CodeBuddy 的 frontmatter**，正文**原样搬运** ——
改写只会引入偏差，还要对付"哪份是最新"的问题。

⚠️ 这些智能体**不依赖** `AI漫剧智能体工作流/` 那套 Python 运行时 ——
它们把规则**内联**在 System Prompt 里，因此在 CodeBuddy 里**开箱可用**
（这正是"完全融合"的意思：不靠外部项目跑起来）。

| 源规格 | 生成 | 内联与否 |
|---|---|---|
| 给"没有工具的模型" | **本目录的 6 个智能体** | ⭐ 规则**全文内联**（模型读不到文件，必须内联） |
| 给"有工具的 agent" | `AI漫剧智能体工作流/` 那套 | 只给路径（避免同一知识两处维护） |

两种形态**各有用途**，不是谁替代谁：上面这套**独立可用**；
工作流那套**与本仓库的代码联动**（ID 分配 / 一致性 Gate / 漂移检测由代码判）。

═══════════════════════════════════════════════════════════════════
用法
═══════════════════════════════════════════════════════════════════
    python .codebuddy/agents/_build.py            # 重新生成 6 个智能体
    python .codebuddy/agents/_build.py --预览      # 只看清单，不写文件

校验：`python AI漫剧智能体工作流/07-智能体运行时/tests/test_agents.py`
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                       # 仓库根
SRC_DIR = ROOT / "智能体搭建参考md"

# ⚠️ `description` 是**主 Agent 决定何时调用你**的唯一依据（官方文档），
#    故每条都必须写清「**当…时使用**」。不要写成 "一个有用的助手"。
# ⚠️ YAML 安全：值里**不能出现 ASCII 的 `冒号+空格`**（会被解析成映射），
#    中文「：」不受影响 —— 故本表统一用全角。
SOURCES: list[dict[str, str]] = [
    {
        "src": "AI剧本创作｜2分钟AI漫剧工业化导演与爆款编剧智能体完整迁移版.md",
        "name": "manju-script-creator",
        "desc": "AI 漫剧剧本创作（2 分钟工业化短剧）- 当需要把原始故事 / 小说 / 一句话创意做成**可投产的 2 分钟 AI 漫剧剧本**时使用，覆盖工业化分集、10 大记忆点角色、每角色 10 项记忆资产、爆款标签、群像差异化、情绪线与黑化/成长/反转路线。例：「把这部小说改编成 AI 漫剧」「给我一份 40 集分集大纲」「这个主角怎么做出记忆点」。产出剧本 + 全人物总建模 + 分集结构 + 视觉统一方案。",
        "tools": "read_file, write_to_file, replace_in_file, search_file, search_content, list_dir",
    },
    {
        "src": "AI漫剧服化道智能体_FULL_PORTABLE_AGENT_SPEC_V2.md",
        "name": "manju-costume-prop-engine",
        "desc": "AI 漫剧服化道引擎（FULL PORTABLE AGENT SPEC V2.0）- 当需要把小说 / 剧本**视觉化**成世界观、角色三视图、服装、道具、场景、表情、动作资产时使用，覆盖锁定系统、局部修改、版本控制、一致性检查与中英双语提示词。例：「女刺客，黑衣，赛博朋克」「给这个角色出三视图」「只改她的发色」。产出视觉资产 + 一致性锁定 + 双语提示词。",
        "tools": "read_file, write_to_file, replace_in_file, search_file, search_content, list_dir, image_gen",
    },
    {
        "src": "AI漫剧资产库角色道具｜完整智能体迁移配置.md",
        "name": "manju-asset-library",
        "desc": "AI 漫剧资产库（角色 / 道具设定图）- 当需要生成**标准化、可复用、高一致性**的角色或道具设定图时使用，覆盖自动补全（年龄 / 面部 / 发型 / 服装材质 / 配色 / 装备 / 特殊身体特征）与固定版式（16:9，左侧人物特写 + 右侧正侧背三视图）。例：「红发女骑士角色设定图」「出一把赛博朋克武士刀的道具设定图」。产出补全后的设定 + 标准画布 + 提示词 + 图像。",
        "tools": "read_file, write_to_file, replace_in_file, search_file, search_content, list_dir, image_gen",
    },
    {
        "src": "Suno_歌词大师｜完整智能体迁移配置.md",
        "name": "manju-suno-lyric-master",
        "desc": "Suno 歌词大师 - 当需要为 AI 漫剧 / 短剧写**可直接投给 Suno 的完整歌曲**时使用，覆盖歌词结构、押韵、Hook 与副歌规则、Suno 标记、Style Prompt 组成与禁忌、曲风模板、情绪递进、中英混写与商业流行优化。例：「给这部剧写一首主题曲」「一句话主题扩写成完整歌曲」「帮这段歌词配 Style Prompt」。产出歌词 + 结构标记 + Style Prompt。",
        "tools": "read_file, write_to_file, replace_in_file, search_file, search_content, list_dir",
    },
    {
        "src": "分镜导演助手｜完整智能体迁移配置_Markdown.md",
        "name": "manju-storyboard-director",
        "desc": "AI 漫剧分镜导演【先出分镜再出图】- 当需要把文字内容转成**可拍摄的视觉设计**时使用，按三阶段走：纯视觉 Storyboard → 专业镜头拆解 → AI 图像提示词，覆盖景别 / 机位 / 构图 / 运镜 / 光影 / 颜色 / 氛围，以及人物 Identity Lock 与场景 Environment Lock。例：「把这一场做成分镜」「这场戏需要几个镜头」「按分镜出图提示词」。产出视觉分镜 + 镜头拆解 + AI 提示词。",
        "tools": "read_file, write_to_file, replace_in_file, search_file, search_content, list_dir",
    },
    {
        "src": "调音大师班｜完整智能体迁移配置_Markdown.md",
        "name": "manju-audio-tuning-master",
        "desc": "AI 漫剧调音大师班（声音设计）- 当需要做人物声线设计、环境声音、道具 Foley 或剧情声音表现时使用，覆盖年龄感 / 气息 / 颗粒感 / 情绪张力 / 语速 / 停顿 / 空间与收音 / 低频 / 特殊音色，以及标准化声音提示词结构。例：「给女主选个声线」「这段该配什么环境声」「这个人物的人声提示词怎么写」。产出声音设计方案 + 声音提示词。",
        "tools": "read_file, write_to_file, replace_in_file, search_file, search_content, list_dir",
    },
]

FRONT_KEYS = ("name", "description", "tools", "agentMode", "enabled", "enabledAutoRun")
# ⚠️ `description` 是**官方规定**的字段名（不是 `desc`）—— 写错会静默失效：
#    主 Agent 拿不到调用依据 → 这个智能体**永远不会被自动选中**。
FIELD_MAP = {"name": "name", "desc": "description", "tools": "tools"}


def yaml_value(v: str) -> str:
    """安全地写一个 YAML 标量（含冒号/引号时加引号）。"""
    if re.search(r":\s|^[#&*!|>%@`\"'\[{]", v) or v != v.strip():
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


def build_one(item: dict, preview: bool) -> tuple[str, int, int]:
    src = SRC_DIR / item["src"]
    if not src.is_file():
        raise FileNotFoundError(f"源规格不存在：{src}")
    text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")

    # 正文 = 源规格**逐字**（保留其 H1 与「用途/适用」元信息 —— 那是给智能体自己看的）
    body = text.rstrip() + "\n"

    # 出处注记放**正文最前**（一行）—— 便于将来追源，且进 System Prompt 也不浪费
    prov = (f"> 生成自 `智能体搭建参考md/{src.name}`（由 `.codebuddy/agents/_build.py` "
            f"逐字移植）。**改规则请改源规格后重新生成**。\n\n")

    vals = {FIELD_MAP[k]: item[k] for k in FIELD_MAP}
    vals.update({"agentMode": "agentic", "enabled": "true",
                 "enabledAutoRun": "true"})
    fm = "\n".join(f"{k}: {yaml_value(str(vals[k]))}" for k in FRONT_KEYS)
    out = f"---\n{fm}\n---\n\n{prov}{body}"
    dest = HERE / (item["name"] + ".md")
    if not preview:
        dest.write_text(out, encoding="utf-8", newline="\n")
    return item["name"], len(body), len([l for l in lines if l.startswith("#")])


def main() -> int:
    ap = argparse.ArgumentParser(description="移植 智能体搭建参考md → CodeBuddy 子智能体")
    ap.add_argument("--预览", dest="preview", action="store_true",
                    help="只打印清单，不写文件")
    a = ap.parse_args()

    print(f"  源目录：{SRC_DIR}")
    print(f"  源规格 {len(SOURCES)} 份 → 生成 {len(SOURCES)} 个智能体")
    print()
    total = 0
    for it in SOURCES:
        name, n, secs = build_one(it, a.preview)
        total += n
        flag = "（预览）" if a.preview else ""
        print(f"  ✅ {name:30s} 正文 {n:6d} 字符 ｜ {secs:3d} 个标题 {flag}")
    print()
    print(f"  合计正文 {total} 字符（≈ {total / 1024:.0f} KB）")
    print(f"  校验：python AI漫剧智能体工作流/07-智能体运行时/tests/test_agents.py")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
