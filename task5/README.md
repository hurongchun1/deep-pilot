# Task 5：Skills 可复用能力包

本目录以 [AgentSeek content-builder 模板](https://github.com/agentseek-ai/agentseek-templates/tree/main/templates/deepagents/content-builder) 为基础，沿用本仓库 task4 已验证的后端结构，学习 [《Deep Agents 实战》第 7 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/) 的 Skills 机制。工程使用 `deepagents==0.7.8`、Python 3.12 和独立的 `uv.lock`。这里保留内容创作 Agent 的后端和原有 `blog-post`、`social-media` Skills，增加 `skill-guide`、渐进式加载实验与多源覆盖检查。前端不在本目录中。

## 目录

```text
task5/
├── src/task5/agent.py                   # Agent 图与 skill_sources 参数
├── skills/blog-post/SKILL.md            # 模板中的长文 Skill
├── skills/social-media/SKILL.md         # 模板中的社媒 Skill
├── skills/skill-guide/
│   ├── SKILL.md                         # 第 7 章学习指南的元数据与核心指令
│   ├── references/concepts.md           # 按需读取的术语卡
│   └── assets/guide-outline.md          # 按需读取的学习笔记模板
├── experiments/ch07_progressive_disclosure.py
├── tests/test_skills.py
├── COURSE.md                            # 实验过程与观察点
├── .env.example
├── pyproject.toml
└── uv.lock
```

## 无需模型密钥的实验

在 `task5` 目录运行。`uv` 会按本目录的 `pyproject.toml` 和 `uv.lock` 安装 `task5` 及其依赖；也可先显式执行 `uv sync --frozen`：

```powershell
uv run --frozen python experiments/ch07_progressive_disclosure.py
uv run --frozen pytest tests -q
```

脚本直接导入 `deepagents.create_deep_agent` 和 `FilesystemBackend` 来构建最小 Agent，不依赖 `task5.agent`。它使用预设的模型工具调用，依次读取 Skill 正文、参考文档、模板，并断言每轮模型消息里刚好出现已加载的层级；成功时打印 `PASS`。`test_skills.py` 还验证两个目录中同名 Skill 的后者覆盖前者。实验不会调用真实模型或外部服务。

本项目采用 `src/task5/` 布局，但上面的独立实验不需要导入该包。请用 `task5/.venv` 运行实验，以取得锁定的 `deepagents` 等依赖。运行后端应用或项目测试时才会用到 `task5.agent`；VS Code 单独打开 `task5` 目录时，本目录的 `.vscode/settings.json` 会选择 `task5/.venv` 并把 `src` 加入分析路径。

## 连接真实模型

只在 `.env` 不存在时复制配置并填写所选模型的密钥：

```powershell
Copy-Item .env.example .env
uv run --frozen agentseek-api dev --port 2025
```

默认使用 SiliconFlow 的 OpenAI 兼容接口与 `deepseek-ai/DeepSeek-V3.2`。填入 `OPENAI_API_KEY`；切换供应商时，同时调整 `AGENTSEEK_MODEL_PROVIDER`、`AGENTSEEK_MODEL`、对应密钥和 base URL。纯文本模式无需 Tavily 或图像密钥。服务 API 文档位于 <http://127.0.0.1:2025/docs>。也可以运行 `uvx agentseek==0.1.2 doctor` 检查环境，运行 `uvx agentseek==0.1.2 dev` 启动本目录声明的后端。

可用以下请求观察模型是否自行选择 Skill，并检查工具轨迹：

```text
请写一份第 7 章 Skills 学习笔记，使用可复用的学习笔记格式，
解释三层加载并给出一个可运行的实验。请把结果保存为
blogs/ch07-skills/post.md，读取保存的文件确认内容后再回答。
```

观察它是否先看到 `skill-guide` 的描述，再调用 `read_file` 读取 `SKILL.md`，随后按需读取 `references/concepts.md` 和 `assets/guide-outline.md`。真实模型的选择和工具顺序是运行结果，不能仅凭提示词断定成功。

## 改写与扩展

- 新增 Skill：创建 `skills/<name>/SKILL.md`，frontmatter 的 `name` 与目录名相同，`description` 写明触发场景。
- 动态路径：`build_graph(model, skill_sources=["/skills/shared/", "/skills/project/"])`。路径是相对本项目 `FilesystemBackend` 根目录的虚拟绝对路径；同名 Skill 后者优先。
- 增加大篇幅资料：放在 Skill 的 `references/` 或 `assets/`，正文说明何时读取，避免把全部内容放入启动元数据。

详细的实验观察点和第 7 章概念对应关系见 [COURSE.md](COURSE.md)。生成的文章保存在 `blogs/`，该目录已被 Git 忽略。
