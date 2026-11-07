# MyBatis 如何借助 Spring Boot 自动配置接入数据库

## MyBatis starter 自动装配了什么

MyBatis 将 Java Mapper 方法映射为 SQL 语句。Spring Boot 的 MyBatis starter 发现已有 DataSource 后，自动创建 `SqlSessionFactory`、`SqlSessionTemplate`，并扫描 Mapper。它负责把 SQL 层接到 DataSource 上；不负责选择 MySQL 驱动和连接池。

`SqlSessionFactory` 用来创建 SQL 会话；`SqlSessionTemplate` 是 Spring 集成中的线程安全会话入口；Mapper 代理通过它执行对应 SQL。

## 注册 Mapper 并配置字段映射

以下示例以 Spring Boot 3.3、Java 17 和 MySQL 为环境。MyBatis 需要可用的 DataSource，因此项目应有 MySQL 驱动和数据库连接配置；MyBatis starter 选用兼容的 3.0 系列，例如官方发布的 `3.0.5`：

```xml
<dependency>
  <groupId>org.mybatis.spring.boot</groupId>
  <artifactId>mybatis-spring-boot-starter</artifactId>
  <version>3.0.5</version>
</dependency>
<dependency>
  <groupId>com.mysql</groupId>
  <artifactId>mysql-connector-j</artifactId>
  <scope>runtime</scope>
</dependency>
```

先提供连接信息，再让 Mapper 可被扫描，并配置下划线列名到驼峰属性名的映射：

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/student
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

```java
@Mapper
public interface CityMapper {
    @Select("select id, city_name from city where id = #{id}")
    City findById(@Param("id") long id);
}
```

```yaml
mybatis:
  configuration:
    map-underscore-to-camel-case: true
```

这里 `city_name` 可以映射到 `City.cityName`。多个 Mapper 也可在启动类上用 `@MapperScan("com.example.mapper")` 统一扫描。应用启动后可以注入 `CityMapper`，无需手动 `new` 一个实现类。

## MyBatis 如何复用 DataSource

MyBatis starter 检测 Spring 容器中的 DataSource，并把它交给 `SqlSessionFactory`。Mapper 代理随后通过 `SqlSessionTemplate` 执行 SQL。将 HikariCP 换成 Druid，只改变连接池，不改变 Mapper 的职责。Mapper 方法可使用注解 SQL，也可与 XML 映射文件绑定；JdbcTemplate 则是同一 DataSource 上方另一种直接调用 SQL 的方式。

## Mapper 扫描与全局配置的常见问题

1. 只引入 MyBatis starter，没有数据库驱动和连接配置，就期待 Mapper 能运行。
2. Mapper 不在扫描范围内，导致注入失败。
3. 把 `mybatis.configuration.*` 与 `mybatis.config-location` 同时配置；starter 不允许两种全局配置方式并用。
4. 把较早的 `mybatis-spring-boot-starter:2.1.4` 直接用于 Boot 3.3。MyBatis 官方兼容矩阵要求按 Boot 版本选择 starter 系列。

参考：[MyBatis Spring Boot Starter](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/)。原始资料：《数据访问》PDF，第 8—10 页。
