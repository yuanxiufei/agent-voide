# AI漫剧资产库 Agent

> 把一句话变成**可复用的 AI 漫剧视觉资产**：结构化资产卡 + 中英双语提示词 + 图像 + 版本历史。

**它是 `AI漫剧智能体工作流` 的代码实现**（位于工作流内 `07-资产库Agent/`），
不是替代品——**规则从工作流实时读取，本项目不复制一份**（见 §三）。

---

## 一、30 秒上手

```bash
cd 07-资产库Agent

# ① 环境自检（先跑这个）
python main.py doctor

# ② 一句话创建角色 → 自动补全 → 出中英提示词 → 出图 → 落库
python main.py "一个30岁的废土女佣兵，机械左臂，穿旧军用风衣"

# ③ 只改一处（其余自动锁定，不会漂移）
python main.py "把她的头发换成银白色"

# ④ 查库
python main.py list
python main.py show CHR_001
```

> ✅ **无需任何 API Key** —— 规则解析 + 零依赖占位图，**装完 Python 就能跑通全流程**。
> 配置 `MODEL_API_KEY` / `IMAGE_API_KEY` 后自动升级为真实语义解析与真实出图。

---

## 二、它做什么

```text
用户自然语言
    ↓  Router          判断意图（创建/修改/查询）与资产类型
    ↓  解析            规则解析（nl_parser） 或 LLM（llm_client）
    ↓  补全            题材预设（character_agent）或 LLM
    ↓  结构化          资产卡（schema.py，字段对齐工作流的 ASSET_CARD.yaml）
    ↓  Prompt Engine   中英双语 MASTER PROMPT  ← 规则来自工作流
    ↓  Consistency     改一处时锁定其余（Face/Body/Clothing/Equipment）
    ↓  Image Provider  mock（零依赖）/ openai / stability
    ↓  落盘            资产卡 + 提示词 + 图像 + 元数据 + 版本历史
```

**核心价值不是"出图"，而是「一致性」**：同一个角色的多个版本/状态之间，
脸、发型、体型、装备**不会漂移**——这靠 `fixed_features` 指纹锁定 + `Consistency Gate` 实现。

---

## 三、⭐ 与工作流的关系（**必读**）

本项目**只读**工作流，**不复制、不改写**其规则：

| 加载的权威文件 | 提供什么 |
|---|---|
| `02-服化道/引擎/NEGATIVE-PROMPT-LIBRARY.md` | 负面词（通用 30 + 三视图 15 + 按模块 6 组 + FAILURE 修复映射 5 条） |
| `02-服化道/引擎/TURNAROUND-STANDARD.md` | 三视图硬标准 · 版式英文段 · 文字屏蔽（权重 `any text:1.8`）· 质量参数 · 服装 25 字段 / 道具字段 |
| `02-服化道/模板/ASSET_CARD.yaml` | 资产卡字段与 `id_status` 枚举（`schema.py` 已按字段对齐） |
| `00-总控路由.md` | ID 规范（`CHR_`/`CST_`/`PRP_`/`ENV_`…） |

**为什么必须这样**：如果把规则复制进代码，就会出现**两处维护、迟早发散**
——这正是工作流质量守则 §2「单一权威来源」要防的事。

### 运行模式

| 模式 | 何时 | 行为 |
|---|---|---|
| **live**（默认） | 工作流目录在场 | 每次运行**实时读取**，工作流一改立刻跟上 |
| **snapshot** | 独立迁移（无工作流目录） | 先 `python main.py export --snapshot` 生成快照到 `vendor/` |

```bash
python main.py rules              # 看实际加载了什么（条数/来源/内容）
python main.py export --snapshot  # 生成快照（供不含工作流的机器）
```

> `vendor/` **故意不入 Git** —— 快照是工作流规则的副本，入库就会变成两处维护。
> 有工作流时一律 live 读取。

---

## 四、目录结构

```text
07-资产库Agent/
├── README.md              本文件
├── SYSTEM_PROMPT.md       Agent 行为规范（可移植到 CodeBuddy/ChatGPT 等）
├── config.json            运行配置（Provider / 尺寸 / ID 风格 / 工作流路径）
├── requirements.txt       ⚠️ 核心零依赖；仅真实图像 API 需 requests
├── .env.example           环境变量样例（API Key）
├── .gitignore
├── main.py                CLI 入口
│
├── src/
│   ├── rule_source.py     ⭐ 从工作流加载权威规则（只读）
│   ├── schema.py          数据模型 + ID 规范
│   ├── nl_parser.py       规则解析（无需 Key）
│   ├── llm_client.py      LLM 客户端（可选，标准库 urllib）
│   ├── router.py          意图 / 资产类型路由
│   ├── character_agent.py 角色补全（11 题材预设，中英双语）
│   ├── prop_agent.py      道具补全
│   ├── costume_agent.py   服装补全
│   ├── prompt_engine.py   结构化 → 中英 MASTER PROMPT
│   ├── consistency.py     ⭐ 一致性 Gate（改一处锁其余）
│   ├── image_provider.py  Provider 抽象 + mock（零依赖手写 PNG）
│   ├── asset_manager.py   资产库 CRUD + 版本 + 注册表
│   └── agent.py           主编排
│
├── prompts/               本地覆盖目录（默认走工作流规则，见其 README）
├── assets/                资产卡（JSON 入库）
├── output/                图像 / 提示词 / 元数据
└── vendor/                规则快照（gitignored；独立迁移时生成）
```

---

## 五、命令行

| 命令 | 作用 |
|---|---|
| `python main.py "<描述>"` | 创建资产（**默认走这个**） |
| `python main.py "把她的头发换成银色"` | 修改资产（只改指定项，其余锁定） |
| `python main.py probe "<描述>"` | **只出提示词，不出图**（核对提示词质量） |
| `python main.py list [--type] [--world] [--keyword]` | 列出资产库 |
| `python main.py show <ID> [--version]` | 查看资产 + 一致性检查 |
| `python main.py rules` | 显示从工作流加载的权威规则 |
| `python main.py doctor` | 环境自检（规则源 / LLM / Provider / 资产数） |
| `python main.py export [--out x.zip]` | 导出资产 ZIP（跨机迁移） |
| `python main.py export --snapshot` | 导出规则快照到 `vendor/` |

可选参数：`--no-image`（不出图）· `--provider mock|openai|stability` · `--type character|costume|prop|environment`

---

## 六、接入真实模型

```bash
cp .env.example .env      # 填入 Key（.env 已在 .gitignore）
```

| 变量 | 用途 | 不填的后果 |
|---|---|---|
| `MODEL_API_KEY` + `MODEL_BASE_URL` + `MODEL_NAME` | 语义解析 + 视觉精修 | 用规则解析（可接受） |
| `IMAGE_API_KEY` + `IMAGE_BASE_URL` + `IMAGE_MODEL` | 真实出图 | 用 mock 占位图 |

再把 `config.json` 的 `image.provider` 改成 `openai` 或 `stability`。

**兼容任何 OpenAI 格式的服务**：OpenAI · DeepSeek · 智谱 GLM/CogView · 通义 · Moonshot · Ollama · vLLM。

> ⚠️ **Key 绝不入库**——`config.json` / `SYSTEM_PROMPT.md` / 源码里都不得出现（蓝图 §二十一）。

---

## 七、ID 规范（重要裁决）

用户蓝图用的是 `CHAR-001` / `PROP-001` / `COSTUME-001` / `SCENE-001`，
而本工作流的**权威 ID 规范**（`00-总控路由.md` §四）是：

| 类型 | 前缀 |
|---|---|
| 角色 | `CHR_` |
| 服装 | `CST_` |
| 道具 | `PRP_` |
| 场景 | `ENV_` |

`02-服化道/01-资产库出图引擎.md` §〇.3 明文规定「**不得自造前缀**」。
故本项目**采用工作流规范**（架构对齐：与 `ID-REGISTRY` 冲突时以项目既有规范为准），
但通过 `config.json` 的 `id_style` 保留两套字面（`project` / `blueprint`），语义完全相同。

---

## 八、跨电脑迁移

**方式一：连工作流目录一起复制**（推荐，保持 live 模式）

```text
把 AI漫剧智能体工作流/ 整个复制过去 → 打开 07-资产库Agent/ → python main.py doctor
```

**方式二：只带本项目**

```bash
# 在源机器
python main.py export --snapshot          # 生成 vendor/ 规则快照
python main.py export --out assets.zip    # 导出资产
# 目标机器：复制整个 07-资产库Agent/ + 解压 assets.zip → doctor（会显示 snapshot 模式）
```

---

## 九、当前边界（诚实说明）

| 项 | 状态 |
|---|---|
| 角色 / 道具 / 服装 三类资产 | ✅ 已实现 |
| 场景（`ENV_`）资产 | ⚠️ 类型可识别，补全策略较薄（待补预设表） |
| 表情 / 动作（`EXP_` / `POS_`） | ⚠️ ID 规范已预留，未实现 |
| 出图质量 | `mock` 是**版式示意占位图**，不是成图；真实成图需接 Provider |
| 一致性校验 | ✅ 指纹锁定 + 改一处 Gate；② 视觉层比对（图与图）未实现 |
| 批量生产（一次 10 个 NPC） | ❌ 未实现（蓝图 §十八） |

---

## 十、故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `权威规则缺失` | 工作流目录不在预期位置 → 设 `WORKFLOW_ROOT` 环境变量，或先 `export --snapshot` |
| 英文提示词里出现中文 | 该字段没有英文伴生值 → 在 `character_agent` 的预设表里补 `*_en` |
| 出图很慢 | 换小尺寸：改 `config.json` 的 `image.width/height` |
| `MODEL_API_KEY` 未配置 | 正常——自动用规则解析，功能完整 |
