# AI漫剧智能体运行时

> **工作流里每个流程模块，都是一个可独立运行的 agent** —— 本目录是它们的**通用运行时**。

**它是 `AI漫剧智能体工作流` 的代码实现**（位于工作流内 `07-智能体运行时/`），
不是替代品——**规则从工作流实时读取，本项目不复制一份**（见 §三）。

---

## 一、30 秒上手

```bash
cd 07-智能体运行时
python main.py doctor                    # ① 环境自检（先跑这个）
python main.py agents                    # ② 看 7 个 agent 全貌

python main.py init script               # ③ 独立启动某个 agent（01 剧本）
python main.py run script "废土末世，40集"  # ④ 用它干活
python main.py route "这场戏怎么拆分镜"      # ⑤ 不确定进哪个 → 让总控判定
python main.py gate all                  # ⑥ 三门禁一览
```

> ✅ **无需任何 API Key** —— 未配 Key 时输出**可直接粘贴的调用包**
> （System Prompt 已按该 agent 装配好，粘进 ChatGPT/Claude/CodeBuddy 即可）；
> 配置 `MODEL_API_KEY` 后自动变成真实模型调用。

---

## 二、⭐ 七个 agent（每个都可独立运行）

| 编号 | key | agent | 职责 | 门禁 |
|---|---|---|---|---|
| 00 | `orchestrator` | 全流程总控 | 判定阶段 → 路由模块 → 校验交接 | — |
| 01 | `script` | 剧本文本引擎 | 创意 → 大纲 → 剧本 → 分集（含工业化 40 集） | **剧本门禁** |
| 02 | `asset` | 服化道引擎 | 剧本 → VISUAL_BIBLE + 角色/服装/道具/场景 | **资产门禁** |
| 03 | `storyboard` | 分镜导演 | 剧本 + 资产 → 九列分镜表 + 提示词包 | **分镜门禁** |
| 04 | `video` | 视频生成引擎 | 分镜 → 视频提示词 + 生成脚本 + 尾帧链 | — |
| 05 | `audio` | 音乐音频引擎 | 剧本 + 成片 → 歌词 / BGM / 配音 / 调音 | — |
| 06 | `compliance` | 合规审核引擎 | 提示词 + 成片 → 过审优化 + IP 检查 | — |

**"独立运行"是什么意思**：每个 agent 有自己的
**初始化指令**（`init`）、**输入分流**、**输出纪律**、**交付物**、**门禁**
—— 全部从工作流文档里读出来，不需要人再讲一遍上下文。

---

## 三、⭐ 与工作流的关系（**必读**）

### 3.1 只读**工作流**、绝不复制规则

| 加载的权威内容 | 来源 |
|---|---|
| 每个 agent 的**角色知识**（主控 + 引擎） | 各模块的 `00-主控智能体.md` 等 |
| **初始化指令 / 输出纪律 / 输入分流** | 从上述文档里**按段抽取**（工作流自带体例） |
| **资产 ID 命名与交接协议** | `00-总控路由.md` §四 |
| **三门禁判定标准** | `00-总控路由.md` §五 |
| **全局一致性守护（四张单子）** | `00-总控路由.md` §六 |
| 02 的负面词 / 三视图硬标准 / 资产卡字段 | `02-服化道/引擎/*` + `模板/ASSET_CARD.yaml` |

**为什么必须这样**：把规则复制进代码，就会出现**两处维护、迟早发散**
—— 这正是工作流质量守则 §2「单一权威来源」要防的事。

### 3.2 ⭐ 通用是怎么做到的：**声明式注册表**

新增或改造一个流程 agent = **在 `src/registry.py` 加一条**。
之后 CLI、路由、交接清单、门禁、文档清单会**自动**支持它 —— **零代码改动**。

```python
AgentSpec(
    key="storyboard", no="03", name="分镜导演", dir="03-分镜导演",
    role_docs=[...],      # 扮演它必须读的文档
    ref_docs=[...],       # 按需加载的素材
    outputs=[...],        # 交付物
    gate="分镜门禁",       # 门禁 + 判据关键词
    triggers=[...],       # 用户这么说 → 进这个 agent
)
```

### 3.3 两种运行模式

| 模式 | 何时 | 行为 |
|---|---|---|
| **live**（默认） | 工作流目录在场 | 每次运行**实时读取**，工作流一改立刻跟上 |
| **snapshot** | 独立迁移（无工作流目录） | 先 `python main.py export --snapshot` |

---

## 四、命令一览

### 通用（对**任意** agent 都可用）

| 命令 | 作用 |
|---|---|
| `agents` | 列出 7 个 agent（构建自注册表） |
| `init <agent>` | 输出该 agent 的**初始化指令**（独立启动） |
| `run <agent> "<输入>"` | 用它处理输入（有 Key 真调；无 Key 出可粘贴调用包） |
| `route "<输入>"` | 00 总控路由：判定该进哪个 agent |
| `handover <agent> [--file]` | 生成 / 校验该模块的**交接清单** |
| `gate <agent> [文件]` · `gate all` | **门禁**预检 / 三门禁一览 |
| `doc <路径> [--section 关键词]` | 取工作流任意文档（或某一节）原文 |
| `outline` | 列出工作流文档清单（按 agent 分组） |

> `<agent>` 支持 **key / 编号 / 中文名**：`script` = `01` = `剧本文本引擎`

### 02 服化道的**结构化超能力**（唯一带插件的模块）

| 命令 | 作用 |
|---|---|
| `python main.py "一个30岁的废土女佣兵"` | 创建：解析 → 补全 → 中英提示词 → 出图 → 落库 |
| `python main.py "把她的头发换成银白色"` | 修改：**只改指定项，指纹锁定不漂移** |
| `probe` / `list` / `show` | 只出提示词 / 列库 / 看单个 |
| `rules` / `doctor` / `export` | 规则概览 / 自检 / 导出 |

---

## 五、目录结构

```text
07-智能体运行时/
├── README.md              本文件
├── SYSTEM_PROMPT.md       02 资产库 agent 的行为规范（可移植；其余 agent 由工作流文档生成）
├── main.py                统一 CLI
├── config.json / .env.example / requirements.txt
├── src/
│   ├── registry.py        ⭐ 声明式注册表：7 个 agent（加 agent = 加一条）
│   ├── module_loader.py   ⭐ 通用加载器：从工作流装配任意 agent 的角色知识
│   ├── dispatcher.py      ⭐ 总控路由（触发词在注册表，算法在这里）
│   ├── handover.py        ⭐ 交接清单 + 门禁预检
│   ├── runtime.py         ⭐ 通用执行器（装配 → 调用 → 落盘）
│   ├── rule_source.py       02 的规则来源层（只读工作流）
│   ├── schema.py / nl_parser.py / prompt_engine.py / consistency.py
│   ├── character_agent.py / prop_agent.py / costume_agent.py
│   ├── image_provider.py / asset_manager.py / llm_client.py / agent.py
│   └── __init__.py
├── prompts/               本地覆盖目录（默认走工作流规则）
├── assets/ / output/      资产卡 / 生成物（均 gitignore 或运行态）
└── examples/              三份样例资产卡（角色 / 道具 / 服装）
```

---

## 六、接入真实模型

```bash
cp .env.example .env      # 填入 Key（.env 已在 .gitignore）
```

| 变量 | 用途 | 不填的后果 |
|---|---|---|
| `MODEL_API_KEY` + `MODEL_BASE_URL` + `MODEL_NAME` | 全部 agent 的真实推理 | 输出可粘贴调用包（同样可用） |
| `IMAGE_API_KEY` + `IMAGE_BASE_URL` + `IMAGE_MODEL` | 02 的真实出图 | mock 版式示意占位图 |

**兼容任何 OpenAI 格式的服务**：OpenAI · DeepSeek · 智谱 · 通义 · Moonshot · Ollama · vLLM。

> ⚠️ **Key 绝不入库**。

---

## 七、ID 规范（重要裁决）

用户蓝图用 `CHAR-001`，而工作流**权威规范**（`00-总控路由.md` §四）是
`CHR_` / `CST_` / `PRP_` / `ENV_` / `EXP_` / `POS_` / `SHT_` / `VID_` / `AUD_`，
且明文规定「**不得自造前缀**」。故本项目**采用工作流规范**，
通过 `config.json` 的 `id_style` 保留两套字面（`project` / `blueprint`），语义相同。

---

## 八、当前边界（诚实说明）

| 项 | 状态 |
|---|---|
| 7 个 agent 的**装配 / 启动 / 路由 / 交接 / 门禁** | ✅ 已实现（通用，零依赖） |
| 02 服化道的**结构化能力**（资产卡 / 出图 / 指纹锁定） | ✅ 已实现 |
| 其余 5 个模块的**结构化能力** | ⚠️ 依赖 LLM（未配 Key 时只出调用包）——这是**设计选择**：剧本/分镜/歌词的质量本就该由模型负责，硬编码规则只会更差 |
| 场景（`ENV_`）补全 · 表情/动作（`EXP_`/`POS_`） | ⚠️ ID 已预留，未实现 |
| 批量生产（一次 10 个 NPC） | ❌ 未实现 |

---

## 九、故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `权威规则缺失` / `未找到工作流目录` | 把本项目与工作流一起复制；或设 `WORKFLOW_ROOT`；或 `export --snapshot` |
| 某 agent 报「缺 N 份文档」 | 跑 `python main.py outline` 看 ✅/❌ 清单 |
| `route` 判错模块 | 在 `src/registry.py` 的该 agent `triggers` 里补触发词（声明式，改一处即可） |
| 英文提示词里出现中文 | 该字段缺英文伴生值 → 在 `character_agent` 预设表补 `*_en` |
