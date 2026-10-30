# 第 7 章学习笔记：State、Store 与 namespace 的共享范围

> 根据本次讨论、项目代码 `experiments/ch07_backends.py`、`experiments/_scripted.py`、`skills/skill-guide/SKILL.md` 和 `skills/skill-guide/references/concepts.md` 整理。
> 这是项目学习笔记，不是官方文档译文。组织、角色、用户相关的扩展示例为合成教学示例，不代表项目已经实现完整的登录授权系统。

## 一、先分清记忆范围和存储位置

“短期”和“长期”主要描述数据的使用范围，不能仅按数据保存多久判断。

| 使用场景 | 通常选择 | 条件与边界 |
| --- | --- | --- |
| 一次执行中保留数据 | state，不配置 checkpointer | 一次 `invoke()` 或 `stream()` 内可用；下一次调用不会自动恢复 |
| 继续同一会话的任务 | state + checkpointer | 使用同一 `thread_id`，并访问同一份检查点存储 |
| 新会话复用偏好、知识或 Skill | Store + namespace | 使用相同的数据存储和完整 namespace |

- `StateBackend` 把文件放在 state 的 `files` 中。
- checkpointer 保存和恢复线程执行状态；`InMemorySaver` 是内存实现，也可以使用数据库实现。
- `StoreBackend` 把文件操作转换成 Store 记录的读写。
- `InMemoryStore` 可以在同一进程内跨会话共享，但进程退出后数据丢失。
- 需要应用重启后保留数据时，应选择持久化 checkpointer 或 Store。

没有配置 checkpointer 时，默认不会自动创建 `InMemorySaver`。运行中的 state 仍然存在，但没有自动跨调用存档。

同一 Agent 可以同时使用两者：checkpointer 保存各会话进度，Store 保存跨会话共享的 Skills。

## 二、namespace 是什么

namespace 是 Store 中数据的逻辑分组。它通常是由多个字符串组成的元组，不必对应数据库表。

```python
namespace = ("role-skills", "company-a", "engineering")
```

这里三个元素的业务含义由应用约定：

| 元素 | 示例 | 本例中的含义 |
| --- | --- | --- |
| 第一个 | `role-skills` | 业务分类前缀 |
| 第二个 | `company-a` | 组织标识 |
| 第三个 | `engineering` | 角色标识 |

框架不会自动认定第二项是组织、第三项是角色。第一个名称也参与匹配，不能随意改动后还期待读到原数据。

```python
("role-skills", "company-a", "engineering")
("user-skills", "company-a", "engineering")
```

上面是两个不同的数据组。

对同一份 Store 中的具体记录，使用完整 namespace 和 key 定位：

```python
store.put(
    namespace=("role-skills", "company-a", "engineering"),
    key="/code-review/SKILL.md",
    value=file_data,
)
```

namespace 不是权限验证器。应用必须先验证用户身份，再使用可信的组织、用户和角色信息选择数据组；不要向模型或普通用户开放任意查询其他 namespace 的接口。

## 三、lambda rt 到底是什么意思

```python
namespace=lambda rt: (
    "role-skills",
    rt.context.org_id,
    rt.context.role,
)
```

等价于：

```python
def get_namespace(rt):
    return (
        "role-skills",
        rt.context.org_id,
        rt.context.role,
    )

# 构造后端时，把函数本身传进去；运行时由后端调用。
backend = StoreBackend(namespace=get_namespace)
```

`lambda` 接收一个运行时参数 `rt`，返回一个元组。返回元组中可以按需要放多个元素，并非固定两项或三项。

```python
namespace=lambda _rt: ("shared-skills",)  # 单元素元组需要逗号
```

`_rt` 的下划线表示这个例子不使用运行时信息，仍然是一个普通参数。

### 对比：固定的角色 Skill 分组和动态的用户记忆分组

下面两种写法都用元组标识 Store 中的数据分组，但它们的来源和共享维度不同：

```python
# 固定值：在直接操作 Store 时使用这个 namespace
role_namespace = ("role-skills", "company-a", "engineering")

# 动态值：StoreBackend 在运行时根据 context 生成 namespace
user_namespace = lambda rt: (rt.context.user_id, "memories")
```

| 对比项 | 固定的角色 Skill 分组 | 动态的用户记忆分组 |
| --- | --- | --- |
| 元素含义 | `role-skills` 是分类，`company-a` 是组织，`engineering` 是角色 | `user_id` 区分用户，`memories` 是分类 |
| 值如何产生 | 直接写出元组；不会因调用者改变 | 运行时读取 `rt.context.user_id`，返回对应元组 |
| 共享条件 | 在此设计中，组织和角色相同，且分类前缀相同 | 在此设计中，用户 ID 相同，且分类前缀相同 |
| 典型用途 | 同一组织、同一角色共享 Skills | 同一用户的不同会话共享长期偏好 |

例如，`user_id` 为 `user-123` 时，动态函数返回 `("user-123", "memories")`；换成 `user-456`，则返回另一个分组。两个不同的 context 对象只要 `user_id` 相同，就会生成相同的 namespace。

固定元组中的组织和角色不会自动从登录信息变化。如果希望按调用者动态选择角色 Skill，需要像本节前面的例子一样，从 `rt.context.org_id` 和 `rt.context.role` 生成元组。

两种方案要访问同一条记录，都还需要连接同一份 Store 数据，并使用相同的完整 namespace 和 key。相同 namespace 只说明可以定位到同一数据组，不代表内容已成功写入，或已经自动传给模型。元组的顺序也参与区分：`("user-123", "memories")` 和 `("memories", "user-123")` 是不同的分组。

当前项目锁定版本对 namespace 有命名校验：元组不能为空；每项是非空字符串，允许字母、数字以及 `-_.@+:~`，不接受通配符等字符。

## 四、放入哪些字段，就按哪些维度共享

前提：各调用连接到同一份 Store 数据。

| namespace 示例 | 共享范围 |
| --- | --- |
| `("shared-skills",)` | 所有映射到该分组的调用共享 |
| `("role-skills", role)` | 相同角色共享，可能跨组织 |
| `("role-skills", org_id, role)` | 相同组织且相同角色共享 |
| `("user-skills", org_id, user_id)` | 同组织内该用户的不同会话共享 |
| `("session-skills", org_id, user_id, session_id)` | 进一步按会话划分 |

只有角色时，`company-a` 和 `company-b` 的工程师可能访问同一个组。加入 `org_id` 后，这两个组织会访问不同组。

```python
# 同组织、同角色、不同会话：namespace 相同，可以共享。
("role-skills", "company-a", "engineering")

# 同组织、不同角色：namespace 不同。
("role-skills", "company-a", "data")

# 不同组织、同角色：namespace 也不同。
("role-skills", "company-b", "engineering")
```

这里没有按 `thread_id` 划分，因此是否同一会话不影响分组。

## 五、org_id 和 role 从哪里来

这些字段需要应用定义，再在执行 Agent 时传入。框架不会从聊天内容或 `sources_by_role` 自动生成。

下面是扩展示意，需要搭配项目中的相关导入、模型和 Store 使用：

```python
@dataclass(frozen=True)
class UserContext:
    org_id: str
    role: str


graph = create_deep_agent(
    model=model,
    context_schema=UserContext,
    backend=CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/role/": StoreBackend(
                namespace=lambda rt: (
                    "role-skills",
                    rt.context.org_id,
                    rt.context.role,
                )
            ),
        },
    ),
    store=store,
    skills=["/skills/role/"],
)

graph.invoke(
    {"messages": [{"role": "user", "content": "列出可用 Skill"}]},
    context=UserContext(org_id="company-a", role="engineering"),
)
```

示例把身份值写死用于说明流程；实际应用由服务端根据已验证的登录用户动态填写。

```text
用户登录、发送问题
    → 服务端取得可信的组织和角色
    → invoke(context=...) 传入
    → namespace 函数生成数据分组
    → StoreBackend 访问该组文件
```

## 六、CompositeBackend、namespace 和 Skill 路径各做什么

它们分别负责三个层次：

1. `skills=["/skills/role/"]`：指定 Skill 发现目录。
2. `CompositeBackend.routes`：根据文件路径选择后端。
3. `StoreBackend.namespace`：选择该后端访问 Store 中的哪组数据。

按上一节的配置，访问路径的转换如下：

```text
Agent 可见路径：/skills/role/code-review/SKILL.md
    → CompositeBackend 匹配 /skills/role/，剥离此前缀
内部 Store key：/code-review/SKILL.md
    → namespace：(role-skills, company-a, engineering)
    → 查找并返回文件
```

因此，预填这个路由对应的 Store 时，key 应是 `/code-review/SKILL.md`。直接使用 StoreBackend、没有 CompositeBackend 路由时，则保留 Agent 使用的完整文件路径。

`sources_by_role` 是另一种做法：应用先根据角色选择目录，再将目录列表传给 `skills`。

```python
sources_by_role = {
    "engineering": ["/skills/engineering/"],
    "data": ["/skills/data/"],
}
skill_sources = sources_by_role[user_role]
```

这个字典不会自动设置 `rt.context.role`。仅选择 Skill 目录控制的是发现范围；若其他目录仍可由同一个文件后端读取，就没有形成完整的访问隔离。

## 七、与渐进式加载的关系

Skill 是包含 `SKILL.md` 的目录，还可以有 `references/`、`assets/` 和 `scripts/`。

无论文件位于 state、Store 还是磁盘，均需区分“后端保存完整文件”和“模型收到哪些内容”：

| 阶段 | 模型收到的内容 |
| --- | --- |
| 发现 Skill | 名称、描述和文件路径 |
| 调用 read_file 读取 SKILL.md 后 | 正文通过工具结果进入后续消息 |
| 按需读取参考资料、模板或脚本后 | 所读取资源的内容 |

Python 的 `read_text()` 可以先读取完整文件并注入 state，这不等于把正文直接发给模型。渐进式加载关注的是模型上下文。

Skill 提供流程指导，Tool 执行具体操作；保存、恢复或共享这些文件则由后端和存储机制承担。

## 八、回到项目代码验证

在 `task5` 目录执行：

```powershell
uv run --frozen python experiments/ch07_backends.py
```

重点对照以下函数和断言：

- `state_backend_case()`：输入 `files` 后，首轮模型上下文包含 `STATE_MARKER`。
- `store_backend_case()`：Store 预填一次，两个不同线程的请求都包含 `STORE_MARKER`。
- `composite_tenant_case()`：team-a 和 team-b 的请求分别只包含自己的描述标记。
- `role_sources_case()`：工程和数据角色分别只发现指定目录下的 Skills。

这些是代码设置的检查点；本次文档整理未重新执行实验。现有实验使用预设模型，验证元数据发现和后端行为，不证明真实模型一定会选择并执行某个 Skill。

建议从 `composite_tenant_case()` 开始，将 `context → namespace → Store key → 模型上下文断言` 对照阅读，再回看角色目录选择实验，比较“选择数据分组”和“选择发现目录”的区别。
