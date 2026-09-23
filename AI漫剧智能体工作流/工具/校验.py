#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI漫剧智能体工作流 · 一致性校验工具
================================================

用途：改动本技能库后跑一次，自动检出「看起来对、实际不一致」的问题。

覆盖 5 类检查：
  1. 引用完整性 —— 路径式引用是否指向真实文件（断链）
  2. 机制覆盖   —— 某机制的关键词是否在它该出现的所有文件里都出现了
  3. 禁用前缀   —— 已废弃的 ID 前缀是否残留（SHOT_ / SCN_ / SHO_ / MUS_EP）
  4. 口径一致   —— 同一数字口径（十类 / 八法）是否跨文件一致
  5. 交付包字段 —— 各模块交付包是否含 ID 与未决项字段

用法：
    python 工具/校验.py              # 全量检查
    python 工具/校验.py -v           # 显示通过的项
    python 工具/校验.py --only 机制   # 只跑某一类

退出码：0 = 全部通过；1 = 存在失败项

设计说明：
  规则以声明式表格写在文件顶部，新增检查只需加一条规则，无需改逻辑。
  这源于一个真实教训——改主控后忘记同步模板，导致用户复制到的仍是被取代的旧格式。
  详见 .codebuddy/memory/feedback-layer-sync.md
"""

import os
import re
import sys
from collections import defaultdict

# ─────────────────────────────────────────────────────────────
# 0. 环境
# ─────────────────────────────────────────────────────────────

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 工作区根（技能库的上一层）——用户原始规格放在其 data/ 下
WORKSPACE = os.path.dirname(ROOT)

# 项目级目录前缀：这些路径是「项目中才会有」的，库内不存在属正常，不报断链
PROJECT_INTERNAL_PREFIXES = (
    "00_PROJECT/", "01_WORLD/", "02_CHARACTERS/", "03_COSTUMES/", "04_PROPS/",
    "05_ENVIRONMENTS/", "06_EXPRESSIONS/", "07_POSES/", "08_STORYBOARDS/",
    "09_SHOTS/", "10_CONSISTENCY/", "AI_DRAMA_PROJECT/",
)

# 源仓库（GitHub）目录：清单里列出的是「待抓取的源文件名」，库内不存在属正常
SOURCE_REPO_DIRS = (
    "分镜/", "角色/", "场景/", "风格/", "工具/", "文档/", "音乐/",
    "参考素材/", "SD2审核筛查/",
)

# 跨文件引用的「内嵌 references」：源 skill 自带的参考库章节，不是独立文件
EMBEDDED_PREFIXES = ("references/",)

EXT = (".md", ".yaml", ".yml")


# ─────────────────────────────────────────────────────────────
# 1. 规则表（声明式 —— 新增检查改这里）
# ─────────────────────────────────────────────────────────────

# 机制覆盖规则：keyword 必须出现在 must_in 列出的每个文件里
MECHANISM_RULES = [
    {
        "name": "ID 注册表机制",
        "keyword": "ID-REGISTRY",
        "must_in": [
            "README.md",
            "00-总控路由.md",
            "快速部署指南.md",
            "03-分镜导演/README.md",
            "03-分镜导演/主工作流/storyboard-director-pro.md",
            "03-分镜导演/分镜导演-完整合并版.md",
            "02-服化道/README.md",
            "02-服化道/模板/PROJECT_STATE.yaml",
            "02-服化道/模板/ASSET_CARD.yaml",
            "02-服化道/项目骨架/README.md",
            "04-视频生成/README.md",
            "04-视频生成/模板/视频生成脚本模板.md",
            "05-音乐音频/README.md",
            "05-音乐音频/模板/音频工程规范模板.md",
            "01-剧本文本/README.md",
            "01-剧本文本/00-主控智能体.md",
            "01-剧本文本/模板/剧本与角色小传模板.md",
            "06-合规审核/模板/风险报告模板.md",
        ],
    },
    {
        "name": "未决项跟踪机制",
        "keyword": "OPEN-ISSUES",
        "must_in": [
            "README.md",
            "00-总控路由.md",
            "01-剧本文本/00-主控智能体.md",
            "01-剧本文本/模板/剧本与角色小传模板.md",
            "06-合规审核/README.md",
            "06-合规审核/00-主控智能体.md",
            "06-合规审核/模板/风险报告模板.md",
            "05-音乐音频/模板/音频工程规范模板.md",
            "04-视频生成/模板/视频生成脚本模板.md",
        ],
    },
    {
        "name": "风险口径十类",
        "keyword": "十类",
        "must_in": [
            "06-合规审核/00-主控智能体.md",
            "06-合规审核/README.md",
            "06-合规审核/模板/风险报告模板.md",
        ],
    },
    {
        "name": "过审优化八法",
        "keyword": "八法",
        "must_in": [
            "06-合规审核/00-主控智能体.md",
            "06-合规审核/README.md",
            "06-合规审核/模板/风险报告模板.md",
        ],
    },
    {
        "name": "视频工程重试层",
        "keyword": "原参数重试",
        "must_in": [
            "04-视频生成/00-主控智能体.md",
            "04-视频生成/README.md",
            "04-视频生成/模板/视频生成脚本模板.md",
        ],
    },
    {
        "name": "视频双锚定机制",
        "keyword": "空间锚",
        "must_in": [
            "04-视频生成/00-主控智能体.md",
            "04-视频生成/README.md",
            "04-视频生成/模板/视频生成脚本模板.md",
        ],
    },
    {
        "name": "表情库英文描述词",
        "keyword": "英文描述词",
        "must_in": [
            "02-服化道/引擎/EXPRESSION-POSE-LIBRARY.md",
        ],
    },
    {
        "name": "光影三源分工",
        "keyword": "光影设计的三个来源",
        "must_in": [
            "02-服化道/引擎/TURNAROUND-STANDARD.md",
        ],
    },
    {
        "name": "自检工具入口",
        "keyword": "工具/校验.py",
        "must_in": [
            "README.md",
            "快速部署指南.md",
            "工具/README.md",
        ],
    },
    {
        "name": "五张单子口径",
        "keyword": "五张单子",
        "must_in": [
            "README.md",
            "00-总控路由.md",
        ],
    },
    {
        "name": "Suno 歌词引擎（三主控结构）",
        "keyword": "02-Suno歌词引擎.md",
        "must_in": [
            "README.md",
            "快速部署指南.md",
            "00-总控路由.md",
            "05-音乐音频/README.md",
            "05-音乐音频/00-主控智能体.md",
            "05-音乐音频/INDEX.md",
        ],
    },
    {
        "name": "Suno 引擎核心能力（调整指令）",
        "keyword": "调整指令",
        "must_in": [
            "05-音乐音频/02-Suno歌词引擎.md",
            "05-音乐音频/README.md",
            "05-音乐音频/INDEX.md",
        ],
    },
    {
        "name": "Suno 引擎短剧档位（实跑补入）",
        "keyword": "短剧时长",
        "must_in": [
            "05-音乐音频/02-Suno歌词引擎.md",
            "05-音乐音频/_规格原文/README.md",
            "05-音乐音频/示例演示/01-Suno引擎实跑验证.md",
        ],
    },
    {
        "name": "Suno 引擎项目接线（实跑补入）",
        "keyword": "项目接线",
        "must_in": [
            "05-音乐音频/02-Suno歌词引擎.md",
            "05-音乐音频/_规格原文/README.md",
        ],
    },
    {
        "name": "04 实跑验证示例",
        "keyword": "实跑验证",
        "must_in": [
            "05-音乐音频/README.md",
            "05-音乐音频/示例演示/01-Suno引擎实跑验证.md",
        ],
    },
    {
        "name": "主示例主题曲回流（六模块闭环）",
        "keyword": "AUD_SNG_001",
        "must_in": [
            "示例演示/01-全流程走通.md",
        ],
    },
    {
        "name": "实跑验证示例被引用",
        "keyword": "01-Suno引擎实跑验证.md",
        "must_in": [
            "示例演示/01-全流程走通.md",
            "示例演示/README.md",
            "05-音乐音频/README.md",
        ],
    },
    {
        "name": "视觉分镜引擎（01 双引擎结构）",
        "keyword": "视觉分镜引擎.md",
        # 注：不含引擎文件自身——它在文内自称「本文件」，要求自指文件名属无效检查
        "must_in": [
            "README.md",
            "快速部署指南.md",
            "00-总控路由.md",
            "03-分镜导演/README.md",
            "03-分镜导演/_规格原文/README.md",
        ],
    },
    {
        "name": "视觉分镜引擎核心能力（双 Lock）",
        "keyword": "Identity Lock",
        "must_in": [
            "03-分镜导演/视觉分镜引擎.md",
            "03-分镜导演/README.md",
            "03-分镜导演/_规格原文/README.md",
        ],
    },
    {
        "name": "资产库出图引擎（02 决策/执行两层）",
        "keyword": "01-资产库出图引擎.md",
        # 注：不含引擎文件自身——它在文内自称「本文件」
        "must_in": [
            "README.md",
            "快速部署指南.md",
            "02-服化道/README.md",
            "02-服化道/引擎/TURNAROUND-STANDARD.md",
            "02-服化道/_规格原文/README.md",
        ],
    },
    {
        "name": "资产库出图引擎核心能力（三视图一致性）",
        "keyword": "三视图一致性",
        "must_in": [
            "02-服化道/01-资产库出图引擎.md",
            "02-服化道/README.md",
            "02-服化道/_规格原文/README.md",
        ],
    },
    {
        "name": "出图引擎实跑补丁（材质库扩展 / 资产卡优先）",
        "keyword": "库外世界观",
        "must_in": [
            "02-服化道/01-资产库出图引擎.md",
            "02-服化道/_规格原文/README.md",
        ],
    },
    {
        "name": "出图引擎实跑补丁（补全结果回写）",
        "keyword": "补全结果回写",
        "must_in": [
            "02-服化道/01-资产库出图引擎.md",
            "02-服化道/README.md",
            "02-服化道/_规格原文/README.md",
        ],
    },
    {
        "name": "出图引擎实跑验证示例",
        "keyword": "05-资产库出图实跑验证.md",
        "must_in": [
            "02-服化道/README.md",
            "02-服化道/示例演示/README.md",
            "02-服化道/_规格原文/README.md",
        ],
    },
    {
        "name": "工业化编剧引擎（05 双引擎结构）",
        "keyword": "01-工业化编剧引擎.md",
        # 注：不含引擎文件自身——它在文内自称「本文件」
        "must_in": [
            "README.md",
            "快速部署指南.md",
            "00-总控路由.md",
            "01-剧本文本/README.md",
            "01-剧本文本/_规格原文/README.md",
            "02-服化道/README.md",
        ],
    },
    {
        "name": "工业化编剧引擎核心机制（10 项记忆资产）",
        "keyword": "10 项记忆资产",
        "must_in": [
            "01-剧本文本/01-工业化编剧引擎.md",
            "01-剧本文本/README.md",
            "01-剧本文本/_规格原文/README.md",
        ],
    },
    {
        "name": "架构对齐（P001 / ASSET_CARD / 画风）",
        "keyword": "架构对齐",
        "must_in": [
            "01-剧本文本/README.md",
            "01-剧本文本/_规格原文/README.md",
        ],
    },
    {
        "name": "表情库扩展 50 式（用户素材落地）",
        "keyword": "扩展 50 式",
        "must_in": [
            "02-服化道/引擎/EXPRESSION-POSE-LIBRARY.md",
            "02-服化道/README.md",
        ],
    },
    {
        "name": "视觉分镜引擎站位机制",
        "keyword": "站位与人物调度",
        "must_in": [
            "03-分镜导演/视觉分镜引擎.md",
        ],
    },
    {
        "name": "资产库出图引擎题材范例库",
        "keyword": "题材范例库",
        "must_in": [
            "02-服化道/01-资产库出图引擎.md",
            "02-服化道/README.md",
        ],
    },
    {
        "name": "03 情绪过渡提示词库（素材提炼）",
        "keyword": "情绪过渡提示词库",
        "must_in": [
            "04-视频生成/引擎/情绪过渡提示词库.md",
            "04-视频生成/README.md",
        ],
    },
    {
        "name": "03 动作戏提示词库（素材提炼）",
        "keyword": "动作戏提示词库",
        "must_in": [
            "04-视频生成/引擎/动作戏提示词库.md",
            "04-视频生成/README.md",
        ],
    },
    {
        "name": "平台与工具速查（素材汇总）",
        "keyword": "平台与工具速查",
        "must_in": [
            "README.md",
        ],
    },
    {
        "name": "01 镜头技法扩充库（运镜50 提炼）",
        "keyword": "镜头技法扩充库",
        "must_in": [
            "03-分镜导演/引擎/镜头技法扩充库.md",
            "03-分镜导演/README.md",
        ],
    },
    {
        "name": "工作区素材全清单（统计）",
        "keyword": "资料素材全清单",
        "must_in": [
            "99-源仓库索引/资料素材全清单.md",
            "99-源仓库索引/仓库全清单.md",
        ],
    },
    {
        "name": "规格覆盖率审计（六份规格无遗漏）",
        "keyword": "规格覆盖率审计",
        "must_in": [
            "99-源仓库索引/规格覆盖率审计.md",
        ],
    },
    {
        "name": "编号=执行顺序（重编号后不再需要说明）",
        "keyword": "01-剧本文本",
        "must_in": [
            "README.md",
            "00-总控路由.md",
        ],
    },
    {
        "name": "场景 AI 提示词 12 字段（§128 提炼）",
        "keyword": "场景 AI 提示词格式（12 字段",
        "must_in": [
            "01-剧本文本/01-工业化编剧引擎.md",
        ],
    },
]

# 禁用前缀：pattern 命中即失败，除豁免文件外
# exempt_line 是用在「该行是说明性文字」的正则
FORBIDDEN_RULES = [
    {
        "name": "分镜前缀（应 SHT_）",
        "pattern": r"SHOT_",
        "should_be": "SHT_",
        "exempt_files": ["02-服化道/_archive/*"],
        "exempt_line": r"不是\s*`?SHOT_|SHOT_\s*[→>]|应.*SHT_|已废弃|勿部署|已知过时项",
    },
    {
        "name": "场景前缀（应 ENV_）",
        "pattern": r"SCN_",
        "should_be": "ENV_",
        "exempt_files": ["02-服化道/_archive/*"],
        "exempt_line": r"不是\s*`?SCN_|SCN_\s*[→>]|应.*ENV_|已废弃|勿部署|已知过时项",
    },
    {
        "name": "自造分镜前缀（应 SHT_）",
        "pattern": r"SHO_",
        "should_be": "SHT_",
        "exempt_files": [],
        # 末尾两条：本工具自身的 README 需要「列出」被禁前缀，属说明性文字
        "exempt_line": r"不得自造|曾经|已重写|已废弃 ID 前缀残留|禁用前缀",
    },
    {
        "name": "自造音乐前缀（应 AUD_）",
        "pattern": r"MUS_EP",
        "should_be": "AUD_",
        "exempt_files": [],
        "exempt_line": r"不得自造|曾经|已重写|已废弃 ID 前缀残留|禁用前缀",
    },
    {
        # 来源：AI剧本创作规格原文用 P001 作角色 ID，本项目改用 CHR_XXX
        # （见 01-剧本文本/_规格原文/README.md §四 架构对齐第 1 条）
        "name": "自造角色前缀（应 CHR_）",
        "pattern": r"\bP\d{3}\b",
        "should_be": "CHR_XXX",
        "exempt_files": ["01-剧本文本/_规格原文/*"],
        "exempt_line": r"原文|架构对齐|P001|P00|自造|不使用|不得使用",
    },
]

# 旧口径：这些说法不应出现在「现行口径文件」里（历史说明文件豁免）
STALE_TERMS = [
    {
        "term": "八类",
        "replace_with": "十类",
        "files": [
            "06-合规审核/00-主控智能体.md",
            "06-合规审核/README.md",
            "06-合规审核/模板/风险报告模板.md",
        ],
        "exempt_line": r"→ ?十类|八类 ?[→>]|八类.*合并|补充|原本",
    },
    {
        # 景别系统 6 级 → 7 级（并入用户素材的美式中景）
        "term": "镜头景别系统（6 级）",
        "replace_with": "镜头景别系统（7 级）",
        "files": ["03-分镜导演/视觉分镜引擎.md"],
        "exempt_line": r"→ ?7 ?级|6 ?级 ?[→>]",
    },
    {
        # 角度系统 7 种 → 8 种（并入低机位贴地）
        "term": "摄影机角度系统（7 种）",
        "replace_with": "摄影机角度系统（8 种）",
        "files": ["03-分镜导演/视觉分镜引擎.md"],
        "exempt_line": r"→ ?8 ?种|7 ?种 ?[→>]",
    },
    {
        # 构图系统 6 种 → 9 种（并入中心/前景遮挡/三角）
        "term": "构图系统（6 种）",
        "replace_with": "构图系统（9 种）",
        "files": ["03-分镜导演/视觉分镜引擎.md"],
        "exempt_line": r"→ ?9 ?种|6 ?种 ?[→>]",
    },
    {
        # 光影系统 7 种 → 8 种 + 氛围词
        "term": "光影系统（7 种）",
        "replace_with": "光影系统（8 种 + 氛围词）",
        "files": ["03-分镜导演/视觉分镜引擎.md"],
        "exempt_line": r"→ ?8 ?种|7 ?种 ?[→>]",
    },
    {
        "term": "六法",
        "replace_with": "八法",
        "files": [
            "06-合规审核/00-主控智能体.md",
            "06-合规审核/README.md",
            "06-合规审核/模板/风险报告模板.md",
        ],
        "exempt_line": r"→ ?八法|六法 ?[→>]|前六法|构图六法|原本|补充",
    },
]

# 交付包字段：这些文件应含「ID」与「未决项」相关字段
DELIVERY_RULES = [
    {"file": "03-分镜导演/主工作流/storyboard-director-pro.md", "fields": ["ID 登记", "未决项"]},
    {"file": "03-分镜导演/分镜导演-完整合并版.md", "fields": ["ID 登记", "未决项"]},
    {"file": "04-视频生成/模板/视频生成脚本模板.md", "fields": ["ID 核对", "未决项"]},
    {"file": "05-音乐音频/模板/音频工程规范模板.md", "fields": ["ID 登记", "未决项"]},
    {"file": "01-剧本文本/模板/剧本与角色小传模板.md", "fields": ["ID 分配", "未决项"]},
    {"file": "06-合规审核/模板/风险报告模板.md", "fields": ["ID 核对", "未决项"]},
]

# ─────────────────────────────────────────────────────────────
# 素材完整性：用户提供的规格原文 + 抓取的源 skill —— 这些是「资产」，不得误删
# 依据用户要求：参考 md 很有用，尽量保留、不要删除
# ─────────────────────────────────────────────────────────────

# 必须存在的具体文件（原文归档、模板、索引）
REQUIRED_FILES = [
    # 用户规格原文归档（最高优先级，缺失即为事故）
    "05-音乐音频/_规格原文/调音大师班-完整规格原文.md",
    "05-音乐音频/_规格原文/Suno歌词大师-完整规格原文.md",
    "05-音乐音频/_规格原文/README.md",
    "03-分镜导演/_规格原文/分镜导演助手-完整规格原文.md",
    "03-分镜导演/_规格原文/README.md",
    "02-服化道/_规格原文/AI漫剧资产库-完整规格原文.md",
    "02-服化道/_规格原文/README.md",
    "01-剧本文本/_规格原文/AI剧本创作-完整规格原文.md",
    # 跨模块共享文档模板
    "01-剧本文本/模板/ID-REGISTRY.md",
    "01-剧本文本/模板/OPEN-ISSUES.md",
    # 素材提炼产出的专项库（2026-09-23，来源 data/资料/）
    "02-服化道/引擎/EXPRESSION-POSE-LIBRARY.md",
    "02-服化道/01-资产库出图引擎.md",
    "03-分镜导演/视觉分镜引擎.md",
    "03-分镜导演/引擎/镜头技法扩充库.md",
    "04-视频生成/引擎/情绪过渡提示词库.md",
    "04-视频生成/引擎/动作戏提示词库.md",
    "平台与工具速查.md",
    "99-源仓库索引/资料素材全清单.md",
    "99-源仓库索引/规格覆盖率审计.md",
    # 各模块源文件映射清单
    "02-服化道/源skill映射/INDEX.md",
    "99-源仓库索引/仓库全清单.md",
    # 自检工具
    "工具/校验.py",
    "工具/提取目录.py",
    "工具/README.md",
]

# 工作区级素材（在技能库目录**之外**）——用户的原始规格来源，最不该丢
# 注意：若整个技能库被拷到别处（data/ 不存在），本项自动跳过并提示，不算失败
REQUIRED_WORKSPACE_FILES = [
    "AI漫剧服化道智能体_FULL_PORTABLE_AGENT_SPEC_V2.md",
    "AI漫剧资产库角色道具｜完整智能体迁移配置.md",
    "AI剧本创作｜2分钟AI漫剧工业化导演与爆款编剧智能体完整迁移版.md",
    "Suno_歌词大师｜完整智能体迁移配置.md",
    "分镜导演助手｜完整智能体迁移配置_Markdown.md",
    "调音大师班｜完整智能体迁移配置_Markdown.md",
]

# 目录最小文件数（防批量误删）
REQUIRED_DIR_MIN = [
    ("03-分镜导演/源skill", 10, "分镜源 skill"),
    ("03-分镜导演/_规格原文", 2, "分镜导演规格原文归档"),
    ("02-服化道/_规格原文", 2, "资产库规格原文归档"),
    ("01-剧本文本/_规格原文", 1, "AI剧本创作规格原文归档"),
    ("02-服化道/源skill库", 22, "服化道源 skill（4 类）"),
    ("02-服化道/引擎", 8, "服化道引擎规则集"),
    ("02-服化道/模板", 5, "服化道记录模板"),
    ("05-音乐音频/_规格原文", 3, "规格原文归档"),
    ("05-音乐音频/示例演示", 1, "引擎实跑验证示例"),
    ("01-剧本文本/模板", 3, "剧本模板（含 ID/未决项）"),
    ("示例演示", 2, "端到端示例"),
]


# ─────────────────────────────────────────────────────────────
# 2. 工具函数
# ─────────────────────────────────────────────────────────────

def walk_files():
    """返回 (绝对路径, 相对路径) 列表，仅 md/yaml。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for fn in filenames:
            if fn.endswith(EXT):
                ap = os.path.join(dirpath, fn)
                out.append((ap, os.path.relpath(ap, ROOT).replace("\\", "/")))
    return sorted(out, key=lambda x: x[1])


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def match_glob(rel, pattern):
    """极简 glob：仅支持 * 通配，按目录前缀匹配。"""
    if pattern.endswith("/*"):
        return rel.startswith(pattern[:-1])
    return rel == pattern


# ─────────────────────────────────────────────────────────────
# 3. 检查实现
# ─────────────────────────────────────────────────────────────

def check_references(files):
    """检查 1：路径式引用（含 / 的 .md/.yaml）是否指向真实文件。"""
    failures = []
    all_basenames = {os.path.basename(ap) for ap, _ in files}

    # 只抓反引号内的路径式引用
    ref_re = re.compile(r"`([^`\n|]*?/[^`\n|]*?\.(?:md|yaml|yml))`")

    for ap, rel in files:
        text = read(ap)
        for m in ref_re.finditer(text):
            ref = m.group(1).strip().split("#")[0]
            if not ref or ref.startswith(("http://", "https://", "//")):
                continue
            # glob 通配（如 引擎/*.md）——非具体文件引用
            if "*" in ref or "?" in ref:
                continue
            # 项目内部路径：库内不存在属正常
            norm = ref.lstrip("./")
            if any(norm.startswith(p) for p in PROJECT_INTERNAL_PREFIXES):
                continue
            # 源仓库待抓文件清单
            if any(norm.startswith(p) for p in SOURCE_REPO_DIRS):
                continue
            # 源 skill 内嵌 references 章节
            if any(norm.startswith(p) for p in EMBEDDED_PREFIXES):
                continue
            # 相对本文件解析
            cand1 = os.path.normpath(os.path.join(os.path.dirname(ap), ref))
            # 相对项目根解析
            cand2 = os.path.normpath(os.path.join(ROOT, ref))
            if os.path.exists(cand1) or os.path.exists(cand2):
                continue
            # 同名文件在别处存在 → 属简写引用，降级为提示，不算失败
            if os.path.basename(ref) in all_basenames:
                continue
            line_no = text[: m.start()].count("\n") + 1
            failures.append({
                "rule": "断链引用",
                "file": rel,
                "line": line_no,
                "text": f"引用 `{ref}`",
                "should_be": "",
            })
    return failures


def check_mechanisms(files):
    """检查 2：机制关键词是否在应出现的文件里都出现了。"""
    contents = {rel: read(ap) for ap, rel in files}
    failures = []
    for rule in MECHANISM_RULES:
        missing = [f for f in rule["must_in"] if rule["keyword"] not in contents.get(f, "")]
        # 文件本身不存在也要报
        nonexistent = [f for f in rule["must_in"] if f not in contents]
        if missing or nonexistent:
            failures.append({
                "rule": rule["name"],
                "keyword": rule["keyword"],
                "missing": missing,
                "nonexistent": nonexistent,
            })
    return failures


def check_forbidden(files):
    """检查 3：已废弃 ID 前缀残留。"""
    failures = []
    for rule in FORBIDDEN_RULES:
        pat = re.compile(rule["pattern"])
        ex_line = re.compile(rule["exempt_line"]) if rule["exempt_line"] else None
        for ap, rel in files:
            if any(match_glob(rel, g) for g in rule["exempt_files"]):
                continue
            for i, line in enumerate(read(ap).splitlines(), 1):
                if pat.search(line) and not (ex_line and ex_line.search(line)):
                    failures.append({
                        "rule": rule["name"],
                        "file": rel,
                        "line": i,
                        "text": line.strip()[:100],
                        "should_be": rule["should_be"],
                    })
    return failures


def check_stale_terms(files):
    """检查 4：旧口径词残留。"""
    contents = {rel: read(ap) for ap, rel in files}
    failures = []
    for rule in STALE_TERMS:
        ex_line = re.compile(rule["exempt_line"]) if rule["exempt_line"] else None
        for rel in rule["files"]:
            text = contents.get(rel)
            if text is None:
                failures.append({"rule": f"旧口径「{rule['term']}」", "file": rel,
                                 "line": 0, "text": "文件不存在", "should_be": rule["replace_with"]})
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rule["term"] in line and not (ex_line and ex_line.search(line)):
                    failures.append({
                        "rule": f"旧口径「{rule['term']}」→ 应为「{rule['replace_with']}」",
                        "file": rel, "line": i,
                        "text": line.strip()[:100], "should_be": rule["replace_with"],
                    })
    return failures


def check_delivery_fields(files):
    """检查 5：交付包字段完整性。"""
    contents = {rel: read(ap) for ap, rel in files}
    failures = []
    for rule in DELIVERY_RULES:
        text = contents.get(rule["file"])
        if text is None:
            failures.append({"rule": "交付包字段", "file": rule["file"], "line": 0,
                             "text": "文件不存在", "should_be": ""})
            continue
        for field in rule["fields"]:
            if field not in text:
                failures.append({"rule": f"交付包缺字段「{field}」", "file": rule["file"],
                                 "line": 0, "text": f"未找到 {field}", "should_be": field})
    return failures


# ─────────────────────────────────────────────────────────────
# 4. 主流程
# ─────────────────────────────────────────────────────────────

def check_assets(files):
    """检查 6：素材完整性 —— 参考 md / 规格原文是否被误删。

    依据用户明确要求：参考的 md 很有用，尽量保留、不要删除。
    注意：本检查直接查文件系统（不依赖 walk_files 的扩展名过滤），
          否则 .py 等非 md/yaml 文件会被误判为缺失。
    """
    failures = []

    for req in REQUIRED_FILES:
        if not os.path.exists(os.path.join(ROOT, req)):
            failures.append({
                "rule": "素材缺失",
                "file": req,
                "line": 0,
                "text": "该文件应存在但未找到（是否被误删？）",
                "should_be": "恢复该文件",
            })

    for d, min_n, desc in REQUIRED_DIR_MIN:
        absdir = os.path.join(ROOT, d)
        if not os.path.isdir(absdir):
            n = 0
        else:
            n = sum(len(fns) for _, _, fns in os.walk(absdir))
        if n < min_n:
            failures.append({
                "rule": "素材缺失",
                "file": f"{d}/（{desc}）",
                "line": 0,
                "text": f"实际 {n} 个文件，应不少于 {min_n} 个（是否被批量误删？）",
                "should_be": f"补回至 ≥ {min_n} 个",
            })

    # 工作区级素材：仅在 data/ 存在时核对（库被拷到别处则跳过）
    data_dir = os.path.join(WORKSPACE, "data")
    if os.path.isdir(data_dir):
        # 只按「文件名」递归匹配，不绑定目录结构
        # ——用户会整理 data/ 布局（如把规格移入 智能体搭建参考md/），
        #   硬编码路径会反复失效，而本检查的目的是「防丢内容」而非「防移位置」
        names = set()
        for _, _, fns in os.walk(data_dir):
            names.update(fns)
        for req in REQUIRED_WORKSPACE_FILES:
            if req not in names:
                failures.append({
                    "rule": "原始规格缺失",
                    "file": f"data/**/{req}",
                    "line": 0,
                    "text": "工作区 data/ 下未搜到该原始规格（是否被误删？）",
                    "should_be": "恢复该文件",
                })
    return failures


def check_text_integrity(files):
    """检查 7：文本完整性 —— 全角括号配平 + 已知损坏指纹。

    背景（2026-09-23 实际事故）：
      用 PowerShell 批量替换中文文本时，`@(@("a","b"))` 这类**单元素数组会被展开**，
      于是 `foreach` 拿到的是字符串而非数组，`.Replace($pair[0], $pair[1])`
      退化成**字符级替换**（`$pair[0]` 取到的是首字符）：
        · 想替换「视觉分镜引擎.md …」→ 实际把全文所有「视」换成了「觉」
        · 想替换「676 行 / 27.4 KB」  → 实际把全文所有「6」换成「7」再把「7」换成「3」
      结果 3 个文件被静默损坏，而当时没有任何检查能发现。

    **最可靠的信号 = 全角括号不配对**：正常中文文档里 `（` 与 `）` 逐行配平，
    字符级替换极易打破它（把 `（` 换成数字/汉字）。
    另加一组**已知损坏指纹**（正常项目不该出现的组合）作双保险。

    ⚠️ 结论：**不要用 PowerShell / sed 做中文内容的批量替换**，改用编辑工具（走 Python）。
    """
    # 已知损坏指纹：这些组合在正常中文里不存在（均由字符级替换产生）
    FINGERPRINTS = [
        ("觉觉", "视觉"),        # 「视觉」被换成「觉觉」
        ("觉频", "视频"),        # 「视频」被换成「觉频」
        ("三觉图", "三视图"),    # 「三视图」被换成「三觉图」
        ("13:9", "16:9"),        # '6'→'3' 类数字损坏
    ]
    # 容忍阈值：中文文档里偶有笑脸 :) 等排版特例，单行不配对不报；
    # 真正的字符级替换会**成片**破坏配平（实测一次事故 = 25 行）
    UNBALANCED_LINE_TOLERANCE = 2
    FILE_IMBALANCE_TOLERANCE = 2
    # 本检查的文档与实现必须「列出」这些指纹（说明性文字），豁免指纹扫描；
    # 括号配平仍检查（这些文件里是 ASCII 括号，不受影响）
    FINGERPRINT_EXEMPT_FILES = ("工具/README.md", "工具/校验.py")

    failures = []

    for ap, rel in files:
        text = read(ap)
        if text is None:
            continue

        # ① 文件级全角括号配平（先看整体，抗单行噪声）
        o, c = text.count("（"), text.count("）")
        if abs(o - c) >= FILE_IMBALANCE_TOLERANCE:
            # 定位最可疑的若干行
            unbal = [(i, l) for i, l in enumerate(text.splitlines(), 1)
                     if l.count("（") != l.count("）")]
            if len(unbal) >= UNBALANCED_LINE_TOLERANCE:
                for i, l in unbal[:5]:
                    failures.append({
                        "rule": "括号不配对（疑似字符级替换损坏）",
                        "file": rel, "line": i,
                        "text": l.strip()[:100],
                        "should_be": "全角括号逐行配平",
                    })
                if len(unbal) > 5:
                    failures.append({
                        "rule": "括号不配对（续）", "file": rel, "line": 0,
                        "text": f"共 {len(unbal)} 行不配对，此处仅列前 5 行",
                        "should_be": "全角括号逐行配平",
                    })

        # ② 已知损坏指纹（豁免本检查自身的文档与实现）
        if rel in FINGERPRINT_EXEMPT_FILES:
            continue
        for bad, good in FINGERPRINTS:
            if bad in text:
                idx = text.find(bad)
                ln = text[:idx].count("\n") + 1
                lines = text.splitlines()
                failures.append({
                    "rule": f"损坏指纹「{bad}」",
                    "file": rel, "line": ln,
                    "text": lines[ln - 1].strip()[:100] if ln <= len(lines) else "",
                    "should_be": good,
                })
    return failures


def check_numeric_claims(files):
    """检查 8：数字声明一致性 —— 文档里写的体积 / 行数 / 个数是否与现状一致。

    背景：数字声明是本项目的**高发失效点**，历史已踩过 4 次以上：
      · 合并版从 77.3KB 去重到 30KB 后，多处文档仍写旧数字
      · 部署指南的「体积表」8 项数据全部过时
      · PowerShell `(Get-Content).Count` 误计行数（1824），正确是 2344——
        而且只改了索引、漏改正文 2 处
      · 根 README 写「102 个文件 / 753 KB」，实际 123 / 1230

    设计要点（三条都是实测踩出来的假阳性，缺一不可）：
      ① **只检查全项目唯一的文件名** —— `00-主控智能体.md` 在 5 个模块都存在，
         无法判断文档指的是哪一个，强行比较必然误报
      ② **跳过含 `→` 的行** —— 那是提炼过程描述（「2344 行 → 481 行」），不是现状声明
      ③ **跳过同一行有 ≥2 个同类数字的** —— 那是「前后对比」写法
         （版本说明「实跑时 724 行…现为 777 行」、错误日志「1824 行 | 2344 行」），
         此时无法判断该拿哪个数字当"现状"，跳过比乱报好
    """
    from collections import defaultdict
    failures = []

    # 文件名 → 出现位置（仅唯一的才参与比对）
    by_base = defaultdict(list)
    for ap, rel in files:
        by_base[os.path.basename(ap)].append(ap)
    uniq = {b: v[0] for b, v in by_base.items() if len(v) == 1}

    local_paths = [ap for ap, _ in files]
    local_cnt = len([ap for ap in local_paths if ap.endswith((".md", ".yaml"))])
    local_kb = sum(os.path.getsize(ap) for ap in local_paths
                   if ap.endswith((".md", ".yaml"))) / 1024

    KB = re.compile(r"`([^`\n]+\.(?:md|py|yaml))`\s*[|｜]\s*\**\s*([0-9]+(?:\.[0-9])?)\s*KB")
    LN = re.compile(r"([0-9]{2,5})\s*行")
    NAME = re.compile(r"`([^`\n]+\.(?:md|yaml))`")
    CNT = re.compile(r"([\u4e00-\u9fa5A-Za-z]+)/?\s*[（(]\s*([0-9]{1,2})\s*个")
    DIRMAP = {"引擎": "02-服化道/引擎", "模板": "02-服化道/模板",
              "源skill库": "02-服化道/源skill库"}

    def line_of(t, pos):
        return t[:pos].count("\n") + 1

    def line_text(t, pos):
        a = t.rfind("\n", 0, pos) + 1
        b = t.find("\n", pos)
        return t[a: b if b != -1 else len(t)]

    def is_before_after(line, pat):
        """同一行出现 ≥2 个同类数字 → 是「前后对比」写法，不判过时。"""
        return len(pat.findall(line)) >= 2

    KB_NUM = re.compile(r"[0-9]+(?:\.[0-9])?\s*KB")
    LN_NUM = re.compile(r"[0-9]+\s*行")

    for ap, rel in files:
        t = read(ap)
        if not t:
            continue
        # ① 体积声明
        for m in KB.finditer(t):
            name, kb = os.path.basename(m.group(1)), float(m.group(2))
            line = line_text(t, m.start())
            if name not in uniq or "→" in line or is_before_after(line, KB_NUM):
                continue
            real = os.path.getsize(uniq[name]) / 1024
            if abs(real - kb) > 0.6:
                failures.append({
                    "rule": f"体积声明过时（{name}）", "file": rel,
                    "line": line_of(t, m.start()),
                    "text": f"写 {kb} KB，实际 {real:.1f} KB",
                    "should_be": f"{real:.1f} KB",
                })
        # ② 行数声明
        for m in LN.finditer(t):
            line = line_text(t, m.start())
            if "→" in line or "->" in line or is_before_after(line, LN_NUM):
                continue
            names = [os.path.basename(x) for x in NAME.findall(line)]
            names = [x for x in names if x in uniq]
            if len(names) != 1:
                continue
            real = read(uniq[names[0]]).count("\n") + 1
            if abs(real - int(m.group(1))) > 2:
                failures.append({
                    "rule": f"行数声明过时（{names[0]}）", "file": rel,
                    "line": line_of(t, m.start()),
                    "text": f"写 {m.group(1)} 行，实际 {real} 行",
                    "should_be": f"{real} 行",
                })
        # ③ 目录个数声明（排除索引 README，它不算一项内容）
        for m in CNT.finditer(t):
            label, n = m.group(1), int(m.group(2))
            sub = DIRMAP.get(label)
            if not sub or not os.path.isdir(os.path.join(ROOT, sub)):
                continue
            real = 0
            for _, _, fns in os.walk(os.path.join(ROOT, sub)):
                real += len([f for f in fns
                             if f.endswith((".md", ".yaml")) and f != "README.md"])
            if real != n:
                failures.append({
                    "rule": f"个数声明过时（{label}）", "file": rel,
                    "line": line_of(t, m.start()),
                    "text": f"写 {n} 个，实际 {real} 个",
                    "should_be": f"{real} 个",
                })
        # ④ 总量声明（排除小数字，如「64 个文件」指工作区素材）
        for m in re.finditer(r"([0-9]{3})\s*个文件", t):
            n = int(m.group(1))
            if abs(n - local_cnt) > 3:
                failures.append({
                    "rule": "总量声明过时", "file": rel,
                    "line": line_of(t, m.start()),
                    "text": f"写 {n} 个文件", "should_be": f"{local_cnt} 个",
                })
    return failures


def check_trees(files):
    """检查 9：目录树一致性 —— README 里画的树是否与实际文件对得上。

    背景（2026-09-23 用户报障）：
      根 README 的目录树出现三类失效，而前 8 类检查**全都发现不了**——
      因为目录树是"人类可读的结构描述"，不是路径式引用（检查 1 只抓 `` `路径` `` 反引号引用）：
        · **模块顺序乱**（迁移到新编号后仍按旧顺序 03→02→04→05→01→06 排列）
        · **漏列真实内容**（`_archive/`、`99-源仓库索引/规格覆盖率审计.md`）
        · **数字过时**（Suno 引擎写 29KB 实为 30.6KB、合并版写 31KB 实为 31.9KB）

    口径（**必须收窄**，否则误报率极高）：
      · **只查「描述仓库结构」的 README** —— 根 `README.md` 与各模块 `0X-*/README.md`
        ❌ 不查：`引擎/`·`模板/`·`_规格原文/`·`源skill库/` 下的文件与 `项目骨架/README.md`，
           因为它们的「树」是**概念结构图 / 骨架示意 / 外部目录树**，本就不该存在于仓库
        （首版未收窄 → 一次误报 45 项：概念图里的 `§4.2`/`C`/`B2`、骨架里的
          `PROJECT_STATE`/`CHARACTER_001`、`data/资料` 的外部目录、ASCII 框线等）
      · 文件条目在该 README **子树内按 basename** 匹配（树里常只写文件名）
      · 跳过**图示块**：多数行含 `→`（接线图），或条目本身是**纯框线字符**
    """
    TREE = re.compile(r"^[│├└─\s]*[│├└]──\s*([^\s←⭐]+)", re.M)
    BOX = re.compile(r"^[─│┌┐└┘├┤┬┴┼\s]+$")
    failures = []

    for ap, rel in files:
        # ① 文件范围收窄
        base_name = os.path.basename(ap)
        if base_name != "README.md":
            continue
        if "项目骨架" in rel or "_archive" in rel or "示例演示" in rel:
            continue
        if rel != "README.md" and not re.match(r"^0[1-6]-[^/]+/README\.md$", rel):
            continue

        text = read(ap)
        if not text:
            continue
        base = os.path.dirname(ap)
        names, dirs = set(), set()
        for dp, dns, fns in os.walk(base):
            names.update(fns)
            dirs.update(dns)
        if not names:
            continue

        for block in re.findall(r"```(?:text)?\n(.*?)```", text, re.S):
            entries = [TREE.match(l).group(1) for l in block.splitlines() if TREE.match(l)]
            if not entries:
                continue
            # ② 跳过图示块
            arrow = sum(1 for l in block.splitlines() if "→" in l)
            if arrow > len(entries) * 0.5:
                continue

            for ent in entries:
                ent = ent.strip().rstrip("/")
                if not ent or ent.startswith(("*", "…", "(")) or ent in (".", ".."):
                    continue
                if BOX.match(ent):            # 纯框线字符（ASCII 框图）
                    continue
                bn = ent.split("/")[-1]
                if "<" in bn or "…" in bn:    # 占位符
                    continue
                is_dir = ent.endswith("/") or "." not in bn
                ok = (bn in dirs) if is_dir else (bn in names)
                if not ok:
                    ln = 0
                    for i, l in enumerate(text.splitlines(), 1):
                        m = TREE.match(l)
                        if m and m.group(1).strip().rstrip("/") == ent:
                            ln = i
                            break
                    failures.append({
                        "rule": f"目录树条目不存在（{'目录' if is_dir else '文件'}）",
                        "file": rel, "line": ln,
                        "text": ent,
                        "should_be": "改为实际存在的名称，或从树中删除",
                    })
    return failures


CHECKS = [
    ("引用完整性", check_references, "路径式引用是否指向真实文件"),
    ("机制覆盖", check_mechanisms, "机制关键词是否在应出现处都出现"),
    ("禁用前缀", check_forbidden, "已废弃 ID 前缀是否残留"),
    ("口径一致", check_stale_terms, "旧口径词是否残留"),
    ("交付包字段", check_delivery_fields, "交付包是否含 ID 与未决项字段"),
    ("素材完整性", check_assets, "参考 md / 规格原文是否被误删"),
    ("文本完整性", check_text_integrity, "全角括号配平与损坏指纹（防字符级替换事故）"),
    ("数字声明", check_numeric_claims, "文档里的体积/行数/个数/总量是否过时"),
    ("目录树一致性", check_trees, "README 里画的树是否与实际文件对得上"),
]


def print_sizes(files):
    """--sizes：打印所有可部署主控/引擎的体积，供部署指南表格刷新。"""
    print("=" * 66)
    print("可部署文件体积清单（供 快速部署指南.md 表格刷新）")
    print("=" * 66)
    targets = []
    for ap, rel in files:
        base = os.path.basename(rel)
        # 主控 / 引擎 / 总控 / 部署指南 / 关键模板
        if base in ("00-主控智能体.md", "00-总控路由.md", "快速部署指南.md",
                    "分镜导演-完整合并版.md", "storyboard-director-pro.md",
                    "视觉分镜引擎.md", "01-资产库出图引擎.md",
                    "01-工业化编剧引擎.md",
                    "01-声音设计引擎.md", "02-Suno歌词引擎.md",
                    "ID-REGISTRY.md", "OPEN-ISSUES.md"):
            targets.append((rel, os.path.getsize(ap)))
    for rel, size in sorted(targets):
        print(f"| `{rel}` | {size / 1024:.1f} KB |")
    print()
    print(f"合计 {len(targets)} 个文件 ｜ 全库 {len(files)} 个文件，"
          f"{sum(os.path.getsize(ap) for ap, _ in files) / 1024:.1f} KB")
    return 0


def main():
    argv = sys.argv[1:]
    verbose = "-v" in argv or "--verbose" in argv
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        if i + 1 < len(argv):
            only = argv[i + 1]

    files = walk_files()

    if "--sizes" in argv:
        return print_sizes(files)
    total_bytes = sum(os.path.getsize(ap) for ap, _ in files)

    print("=" * 66)
    print("AI漫剧智能体工作流 · 一致性校验")
    print("=" * 66)
    print(f"根目录：{ROOT}")
    print(f"文件数：{len(files)} 个 ｜ 体积：{total_bytes / 1024:.1f} KB")
    print()

    all_failures = {}
    for name, fn, desc in CHECKS:
        if only and only not in name:
            continue
        fails = fn(files)
        all_failures[name] = fails
        status = "PASS" if not fails else f"FAIL ({len(fails)})"
        print(f"[{status:>9}] {name} —— {desc}")

    print()
    print("-" * 66)

    grand = 0
    for name, fails in all_failures.items():
        if not fails:
            if verbose:
                print(f"\n✅ {name}：通过")
            continue
        grand += len(fails)
        print(f"\n❌ {name}：{len(fails)} 项")
        for f in fails:
            if "rule" in f and "file" not in f:  # 机制覆盖类
                print(f"   · {f['rule']}（关键词「{f['keyword']}」）")
                for m in f.get("nonexistent", []):
                    print(f"       文件不存在：{m}")
                for m in f.get("missing", []):
                    print(f"       缺关键词：{m}")
            else:
                loc = f"{f['file']}:{f['line']}" if f.get("line") else f["file"]
                print(f"   · [{f['rule']}] {loc}")
                if f.get("text"):
                    print(f"       {f['text']}")
                if f.get("should_be"):
                    print(f"       应改为：{f['should_be']}")

    print()
    print("=" * 66)
    if grand == 0:
        print("✅ 全部通过 —— 无「看起来对、实际不一致」的问题")
        return 0
    print(f"❌ 共 {grand} 项待修 —— 逐项处理后重跑")
    print()
    print("提示：改完权威层（主控/规格）后最容易漏的是实体层：")
    print("      ① 该模块 模板/*  ② 可部署的合并版/总集  ③ 项目骨架/ 下 _README")
    return 1


if __name__ == "__main__":
    sys.exit(main())
