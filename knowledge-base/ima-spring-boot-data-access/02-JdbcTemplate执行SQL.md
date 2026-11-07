# 如何使用 JdbcTemplate 查询和更新数据

## JdbcTemplate 在数据访问链中的位置

`JdbcTemplate` 是 Spring JDBC 的数据库操作 API。它使用 DataSource 获取连接，负责常见的资源管理，并提供查询、更新等方法。Spring Boot 在条件满足时自动配置 JdbcTemplate，可以直接注入业务类。它解决的是“怎样调用 SQL”，不是“用哪个数据库驱动或连接池”。

## 注入 JdbcTemplate 并执行查询与更新

以下示例以 Spring Boot 3.3 和 MySQL 为环境。项目需要 JDBC starter、MySQL 驱动和可用的 DataSource；连接信息由 `spring.datasource.*` 提供：

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
```

在仓库类中注入 JdbcTemplate，使用 `?` 参数占位符传值：

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CityJdbcRepository {
    private final JdbcTemplate jdbc;

    public CityJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findName(long id) {
        return jdbc.queryForObject(
            "select name from city where id = ?", String.class, id);
    }

    public int rename(long id, String name) {
        return jdbc.update("update city set name = ? where id = ?", name, id);
    }
}
```

`queryForObject` 适合预期恰好一行的查询；可能没有结果时，应在调用层明确处理空结果。`update` 返回受影响行数。JdbcTemplate 自身的可调参数使用 `spring.jdbc.template.*`，例如：

```yaml
spring:
  jdbc:
    template:
      max-rows: 500
```

## 它与 DataSource、MyBatis 和 Druid 的关系

JdbcTemplate 和 MyBatis 都在 DataSource 上方执行 SQL。前者直接在 Java 代码中调用 SQL，后者把 SQL 映射到 Mapper 接口。Druid 替换连接池后，JdbcTemplate 的调用代码通常无需改变。

## 查询结果与 SQL 参数的常见误区

1. 用字符串拼接用户输入构造 SQL；值应以占位符参数传入。
2. 以为 `queryForObject` 在零行或多行时会返回 `null`；调用方应按结果数量设计处理。
3. 将 `spring.jdbc.template.*` 与 `spring.datasource.*` 混为一谈。
4. 不检查 `update` 的受影响行数，就假定更新成功。

参考：[Spring Boot 3.3 SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)、[Spring JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)。原始资料：《数据访问》PDF，第 2 页。
