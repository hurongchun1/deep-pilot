# Spring Boot 数据访问知识库｜导读

这组笔记把《数据访问》PDF 拆成可单独检索的知识点。建议把下面 **8 篇 Markdown** 分别导入 ima；本页可作为目录。每篇按自己的逻辑命名小节，分别讲清概念、代码实现、相关知识点和常见误区。

## 主线

```text
MySQL 驱动 → DataSource（HikariCP / Druid）
                         ├→ JdbcTemplate → 直接执行 SQL
                         └→ MyBatis → Mapper 接口 + SQL 映射

Redis 客户端（Lettuce / Jedis）→ RedisConnectionFactory → RedisTemplate
```

Druid 负责 JDBC 连接池，MyBatis 负责 SQL 映射。Redis 有独立的连接工厂。Web Filter 和 Interceptor 是原文末尾的旁支，放在第 8 篇。

| 想查的问题 | 对应笔记 |
| --- | --- |
| 为什么引入 JDBC starter 还要数据库驱动？DataSource 从哪里来？ | `01-JDBC驱动与DataSource自动配置.md` |
| 怎样用 JdbcTemplate 执行 SQL？ | `02-JdbcTemplate执行SQL.md` |
| Druid 怎样替换连接池、统计慢 SQL？ | `03-Druid连接池与监控.md` |
| MyBatis starter 自动创建了什么？ | `04-MyBatis自动配置.md` |
| 注解 SQL、Mapper XML、混合模式怎么选？ | `05-MyBatis-Mapper映射方式.md` |
| Redis 自动配置和 Template 怎么用？ | `06-Redis自动配置与Template.md` |
| Lettuce 与 Jedis 怎么切换？ | `07-Redis客户端选择.md` |
| Servlet Filter、MVC Interceptor 与 Druid Filter 有何区别？ | `08-Filter与Interceptor.md` |

## 示例口径

原 PDF 使用 Spring Boot 2.x 时期的依赖和配置，部分代码在 PDF 页面中被截断。本组笔记统一以 **Spring Boot 3.3、Java 17** 的配置习惯重写教学片段；不是逐字转录。代码假定已有 Spring Boot 项目，并需要 MySQL 或 Redis 服务才能实际运行。第三方依赖版本应与项目版本匹配。凭据在示例中使用环境变量。

原始资料：用户提供的《数据访问》PDF（14 页）。技术核对参考 [Spring Boot SQL 文档](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)、[Spring Boot Redis 文档](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)、[MyBatis starter 文档](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/) 和 [Druid 项目文档](https://github.com/alibaba/druid/blob/master/README.md)。
