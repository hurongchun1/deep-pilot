# Spring Boot 如何配置 JDBC 驱动与 DataSource

## 为什么 JDBC starter 仍需要数据库驱动

JDBC 驱动负责与某一种数据库通信；`DataSource` 是 Java 获取数据库连接的统一接口；连接池在 DataSource 后面复用连接。`spring-boot-starter-jdbc` 引入 Spring JDBC 和连接池相关依赖，却不能替应用决定使用 MySQL、PostgreSQL 还是其他数据库，所以还要引入目标数据库的驱动。

Spring Boot 在 classpath 中发现 JDBC 相关依赖、满足自动配置条件后，根据 `spring.datasource.*` 创建 DataSource。常见默认连接池是 HikariCP。应用自己注册 DataSource Bean 时，默认 DataSource 自动配置会让位。

## 接入 MySQL 并配置 DataSource

以下是已有 Spring Boot 3.3 项目连接 MySQL 的最小配置。Boot parent 或 BOM 管理 JDBC starter 和 MySQL 驱动版本。

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
  <groupId>com.mysql</groupId>
  <artifactId>mysql-connector-j</artifactId>
  <scope>runtime</scope>
</dependency>
```

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/student
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
```

启动后可以注入 `DataSource`，查看实际类型和尝试建立连接；环境变量、数据库实例与库名必须真实存在。诊断自动配置时还可以查看 Spring Boot 的条件评估报告，确认 DataSource 配置是否生效。

## DataSource 如何支撑不同的数据访问方式

DataSource 处在数据库驱动与应用代码之间。`JdbcTemplate` 从它获取连接后直接执行 SQL；MyBatis 通过 `SqlSessionFactory` 复用它，并把 SQL 映射到 Mapper 方法。HikariCP 和 Druid 是 DataSource 的不同连接池实现，替换连接池通常不要求改写上层 SQL。Redis 使用独立的 `RedisConnectionFactory`，不经过 JDBC DataSource。

## 配置驱动与连接池时容易混淆的地方

1. 只引入 JDBC starter，没有数据库驱动、URL 或凭据，就期待连接 MySQL。内嵌数据库是另一种情形。
2. 把连接池参数写到 `spring.jdbc.template.*`；DataSource 和 JdbcTemplate 是两个对象。
3. 手动声明 DataSource 后，仍以为 Boot 会再创建一个默认 HikariCP DataSource。
4. 把 Spring Boot 2.x 的 MySQL 依赖坐标和版本直接混入 Boot 3 项目。

参考：[Spring Boot 3.3 SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)。原始资料：《数据访问》PDF，第 1—3 页。
