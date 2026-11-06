# Skill：制作、渐进式加载与 Deep Agent 接入

Skill 将一项任务的方法、操作步骤及必要资源组织为可复用目录。Agent 先了解有哪些 Skill，再按任务读取详细说明和相关资源，从而避免把全部领域知识一次性放入上下文。

本文示例按 **deepagents 0.7.8、Python 3.12** 核对。代码只保留 Skill 文件内容、关键接入和执行方式；model 表示已创建的模型客户端，workspace 表示已存在工作目录的绝对 Path，省略模型连接及文件批量创建代码。

## 1. Skill 与工具有什么区别

工具提供具体可执行能力，例如读取文件、统计 CSV 行数。Skill 说明什么时候使用这些能力、按什么步骤完成任务，以及如何组织结果。

```text
Skill：告诉 Agent 采用什么方法、遵循什么流程
Tool：提供执行某一步操作的程序入口
Backend：决定文件和执行能力实际由哪里提供
```

Skill 可以只包含操作说明，不必有脚本；也可以引用工具、脚本、模板和资料。添加 Skill 不等于创建了一个与它同名的 Python 工具。

## 2. 一个 Skill 的目录结构

```text
skills/
└── csv-summary/
    ├── SKILL.md
    ├── references/
    │   └── fields.md
    ├── scripts/
    │   └── profile.py
    ├── assets/
    │   └── report-template.md
    ├── examples/
    │   └── sample-report.md
    └── LICENSE
```

| 文件或目录 | 用途 | 是否必需 |
| --- | --- | --- |
| SKILL.md | YAML 元数据，以及 Markdown 任务说明和操作流程 | 是 |
| references/ | 详细规则、接口文档、字段解释等补充资料 | 否 |
| scripts/ | 可执行脚本，例如统计或转换程序 | 否 |
| assets/ | 模板、图片等任务使用的资源 | 否 |
| examples/ | 输入输出示例；目录名是可选组织约定 | 否 |
| LICENSE | 许可证正文或授权说明，不是身份认证证书 | 否 |

标准入口使用大写 **SKILL.md**。不要依赖 Windows 对文件名大小写不敏感的行为，否则换到其他环境可能无法发现 Skill。

references 不是元数据目录。名称、描述、版本等元信息应放在 SKILL.md 的 YAML 区域；references 保存的是具体任务资料。

目录不必全部创建。最小 Skill 只有一个包含 SKILL.md 的目录；资源存在时，应在正文中说明什么时候读取、文件在哪里、如何使用，不能只放文件而不建立关联。

## 3. 怎样编写 SKILL.md

SKILL.md 分为两部分，不是只有 name 和 description：

1. 文件开头的 YAML frontmatter：描述 Skill 的身份与用途。
2. 后面的 Markdown 正文：说明方法、步骤、边界、资源及输出要求。

### 完整的最小文件示例

下面内容放在 workspace/skills/study-plan/SKILL.md。

```markdown
---
name: study-plan
description: 为有明确目标和时间限制的学习任务制定行动计划。用户需要学习路线、练习安排或阶段产物时使用。
---

# 学习计划

1. 提取用户的目标、已有基础、可用时间和预期产物。
2. 读取本 Skill 目录中的 references/outline.md，了解输出结构。
3. 按依赖顺序组织学习、练习和复盘步骤。
4. 区分用户已提供的条件、建议与待确认事项。
5. 输出计划，不把未来安排写成已经完成的结果。
```

### name 与 description

| 字段 | 表示什么 | 如何编写 |
| --- | --- | --- |
| name | Skill 的名称，不是某个脚本的名称 | 使用简短稳定的标识，例如 study-plan，并与父目录名一致 |
| description | Skill 解决什么问题、什么时候适用 | 写清任务场景与触发条件，避免只写“一个很好用的技能” |

按 Agent Skills 规范，name 长度为 1～64，使用小写字母、数字与连字符，不以连字符开头或结尾，也不包含连续连字符；description 应为非空描述，最长 1024 字符。编写时遵循规范，不依赖某个加载器对不规范文件的宽松处理。

license、compatibility、metadata 等是可选字段。license 可以标明许可名称或指向许可证文件；metadata 可放作者、版本等附加信息。它们不是让程序自动安装依赖、执行脚本或获得权限的开关。

## 4. 三阶段加载怎样理解

### 阶段一：发现 Skill，提供轻量信息

框架扫描配置的来源，解析 Skill 的名称、描述和文件路径等信息，再把可用 Skill 的摘要提供给模型。模型因此知道有哪些方法可以使用，而不是先读取所有完整流程。

这里节省的是模型上下文。框架为了解析元数据，可能已在存储层读取 SKILL.md 文件；不能把“未将正文提供给模型”理解成“磁盘上没有读取过正文”。

在核对版本中，SkillsMiddleware 的 before_agent 负责收集元数据，模型请求处理逻辑再将 Skill 列表加入系统提示。

### 阶段二：按任务读取完整说明

模型根据用户请求和 Skill 描述判断相关性，再使用 read_file 读取对应的 SKILL.md。正文进入当前上下文后，模型才获得该 Skill 的详细步骤。

这不是严格按 description 自动执行的路由器。描述帮助模型选择，不保证每次判断都正确；也不能把“配置了 Skill”当成“本轮已经读取 Skill”。

### 阶段三：按需使用支持资源

正文需要详细规则时读取 references，需要模板时使用 assets，需要代码处理时调用相应工具执行 scripts 中的程序。

并非每次都会访问所有目录。脚本也不一定先全文读入模型再执行：已有明确入口时，可以直接由执行工具运行，让输出回到模型。

```text
可用 Skill 摘要
    ↓ 根据任务选择
读取相关 SKILL.md
    ↓ 根据正文需要
读取参考资料 / 使用模板 / 运行脚本
    ↓
根据实际结果继续处理
```

三阶段是渐进式披露思路，不是保证每个请求都会完整走完的固定脚本。

## 5. 制作并接入一个不带脚本的 Skill

### 参考提纲

references/outline.md 的核心内容：

```markdown
# 输出提纲
## 学习目标
## 已知条件
## 阶段安排
每阶段说明练习、产物和验收方式。
## 待确认事项
```

### 接入 Agent 的核心代码

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=workspace, virtual_mode=True),
    skills=["/skills/"],
)
result = agent.invoke({"messages": [{
    "role": "user", "content": "请使用 study-plan，为一周学习 CSV 文件处理制定计划。",
}]})
```

先把上述 Skill 和参考提纲放入工作目录，再配置虚拟路径。`skills=["/skills/"]` 只是声明扫描来源，不会替你创建文件或把另一处的文件自动搬过来。

映射关系是：

```text
真实文件：workspace/skills/study-plan/SKILL.md
虚拟路径：/skills/study-plan/SKILL.md
扫描来源：/skills/
```

模型连接参数在 ChatOpenAI 中设置；create_deep_agent 接收 model 对象，不在这里直接传 api_key 和 base_url。

这个 Skill 没有脚本，仍可以完成方法指导。文件可以预先维护，不必每次调用重新创建。

## 6. Skill 包含脚本时，怎样真正执行

FilesystemBackend 提供文件访问，不提供 execute。scripts 目录中的文件不会因为存在就自动注册为工具，也不会因为被 read_file 读取就自动运行。

执行通常有两种接法：

- 使用 LocalShellBackend 或沙箱 Backend，提供 execute，再在 Skill 中说明脚本入口、输入和结果。
- 注册一个明确的自定义工具，在工具内部运行指定程序，让 Skill 指导何时使用该工具。

下面演示第二种方式。文件仍通过 FilesystemBackend 访问，脚本执行能力来自显式注册的工具，而不是 Backend 本身。

### 脚本与 Skill 的最小内容

scripts/profile.py：

```python
import csv
import json
import sys

with open(sys.argv[1], encoding="utf-8", newline="") as file:
    reader = csv.DictReader(file)
    columns = reader.fieldnames or []
    row_count = sum(1 for _ in reader)
print(json.dumps({"columns": columns, "row_count": row_count}, ensure_ascii=False))
```

csv-summary/SKILL.md：

```markdown
---
name: csv-summary
description: 统计 CSV 的列名与数据行数，需要了解 CSV 概况时使用。
---
# CSV 概况
1. 调用 run_csv_profile 统计已准备的 data.csv。
2. 根据工具返回的 JSON 回答，不凭文件名猜测行数。
```

workspace/data.csv 可以使用下面的表头和两条记录作为输入：

```csv
name,score
Alice,90
Bob,85
```

### 用工具执行脚本并接入 Agent

```python
import subprocess
import sys
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.tools import tool

@tool
def run_csv_profile() -> str:
    """运行 CSV 统计脚本，返回列名与数据行数，不修改原数据。"""
    result = subprocess.run(
        [sys.executable, str(workspace / "skills/csv-summary/scripts/profile.py"),
         str(workspace / "data.csv")],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=10,
    )
    return result.stdout.strip()

agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=workspace, virtual_mode=True),
    skills=["/skills/"],
    tools=[run_csv_profile],
)
result = agent.invoke({"messages": [{
    "role": "user", "content": "请使用 csv-summary，检查 data.csv 的列名与数据行数。",
}]})
```

这个例子的工具用参数列表运行固定脚本，不使用任意 shell 字符串；文件名、程序入口和输入都由示例代码确定。它演示的是明确封装的执行能力，不是让 Skill 文件获得任意系统权限。

Skill 名为 csv-summary，工具名为 run_csv_profile，脚本名为 profile.py，三者可以不同。它们的关系由正文说明和工具注册建立，不依赖同名匹配。

## 7. 怎样判断 Skill 真的被使用

要区分四件事：

| 现象 | 可以说明什么 | 不能直接说明什么 |
| --- | --- | --- |
| Skill 出现在可用列表中 | 来源被发现、元数据可供选择 | 本轮已读取正文 |
| 出现读取 SKILL.md 的工具请求与成功结果 | 正文被读取并返回到调用流程 | 所有步骤必然被遵守 |
| 引用的 references 被实际读取 | 补充资料进入本轮处理 | 脚本已运行 |
| 执行工具返回真实结果 | 相应代码操作发生过 | 所有业务结论都正确 |

工具可以在没有读取 Skill 时被调用；读了 Skill 也可能没有调用预期工具。因此不能只看最后回答说“已使用技能”。可以在 result["messages"] 中定位文件读取、执行请求和对应的工具结果。

## 8. 来源、缓存与权限的边界

- Skill 来源经过 Backend 访问，不强制要求本地磁盘。使用 StateBackend 或 StoreBackend 时，必须确保对应来源里真的存在 Skill 文件。
- 在核对版本中，同名 Skill 按配置来源顺序由后面的覆盖前面的。避免无意使用同名目录导致加载另一份说明。
- 已有 state.skills_metadata 时，加载逻辑会跳过重新扫描。保持同一 thread 的状态时，修改文件后不能假定元数据立刻刷新；正文何时读取也要以实际调用为准。
- system_prompt 放角色和全局要求，Skill 放可按需加载的方法，工具负责执行，Backend 负责存取，职责可以协作但不能互相替代。
- Skill 是任务说明，不是授权凭据。许可证声明也不授予运行时访问权限。工具、文件权限和执行环境的限制仍需单独配置。
- allowed-tools 等可选元数据的支持因实现而异，不把它当成通用的权限提升开关，也不假设写出一个工具名就完成注册。

## 容易混淆的地方

| 易混淆概念 | 正确区别 |
| --- | --- |
| Skill 与 script | Skill 是方法与资源包；脚本只是可选资源之一 |
| name 与脚本文件名 | name 标识 Skill，脚本文件可以有不同名称 |
| description 与正文 | 前者帮助发现和选择，后者提供详细任务流程 |
| references 与 metadata | 前者是补充资料，后者是 SKILL.md 中的附加元数据字段 |
| license 与证书 | license 描述使用授权，不是身份或权限认证证书 |
| examples 与必需目录 | examples 可用于存放示例，不是每个 Skill 必须创建的目录 |
| 配置来源与复制文件 | skills 参数声明到哪里找，不负责创建或搬运文件 |
| 文件可读与脚本可执行 | 读取源码不会自动运行，执行需要工具或执行型 Backend |
| 渐进式加载与固定三步剧本 | 资源按需进入上下文，不保证每轮都使用全部阶段 |
| 发现 Skill 与遵守 Skill | 发现、读取、执行与结果正确需要分别判断 |

## 示例验证范围

精简后的关键配置、Skill 元数据和脚本逻辑已核对；工具执行脚本的核心逻辑已直接验证。没有在整理本文时发送真实模型请求，因此未声称模型一定读取指定文件或按顺序调用全部工具。

## 参考资料

- [Agent Skills 格式规范](https://agentskills.io/specification)
- [Deep Agents：Skills](https://docs.langchain.com/oss/python/deepagents/skills)
- deepagents 0.7.8 的 SkillsMiddleware 实现。在线文档可能已增加功能，使用时需核对实际安装版本。
