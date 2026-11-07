# MyBatis Mapper 如何组织注解与 XML 中的 SQL

## Mapper 接口如何绑定 SQL

Mapper 接口定义 Java 方法，MyBatis 为每个方法找到 SQL 语句。简单 SQL 可以直接写在注解中；需要动态条件或较长 SQL 时，通常放在 Mapper XML 中。**混合模式**指同一个接口里，不同方法分别使用注解和 XML，而不是同一个方法重复定义 SQL。

## 分别使用注解、XML 与混合模式

以下示例以 Spring Boot 3.3、Java 17 和 MySQL 为环境。项目需要 MyBatis starter 3.0.x、MySQL 驱动、可用的 `spring.datasource.*` 连接配置。下面假定 `City` 有 `id`、`name` 字段，接口全限定名为 `com.example.mapper.CityMapper`。

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

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/student
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

### 注解模式

```java
@Mapper
public interface CityMapper {
    @Select("select id, name from city where id = #{id}")
    City findById(@Param("id") long id);
}
```

`#{id}` 是 MyBatis 参数占位写法；不要把用户输入拼进 SQL 字符串。

### XML 模式

接口只保留方法签名，SQL 写在 `src/main/resources/mapper/CityMapper.xml`：

```java
@Mapper
public interface CityMapper {
    City findById(@Param("id") long id);
}
```

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="com.example.mapper.CityMapper">
  <select id="findById" resultType="com.example.domain.City">
    select id, name from city where id = #{id}
  </select>
</mapper>
```

```yaml
mybatis:
  mapper-locations: classpath:mapper/*.xml
  configuration:
    map-underscore-to-camel-case: true
```

`namespace` 对应接口全限定名，`id` 对应方法名，XML 必须进入运行时 classpath。

### 混合模式

例如 `findById` 使用注解，`findByName` 使用 XML。接口只给前者写 `@Select`；XML 只定义后者的 `<select id="findByName">`。同一个方法只保留一份 SQL 定义。

## SQL 映射如何接上 MyBatis 会话与数据源

Mapper 的执行链是：接口方法 → Mapper 代理 → `SqlSessionTemplate` → `SqlSessionFactory` → DataSource → 数据库驱动。注解 SQL 与 XML SQL 都沿用这条链，只是 SQL 定义的位置不同。JdbcTemplate 也使用 DataSource，但由业务代码直接调用 SQL。

## 映射路径、方法名与配置方式的误区

1. XML 文件路径、`namespace`、SQL 节点 `id` 与接口不匹配，出现“找不到映射语句”。
2. 同一方法同时写注解和 XML SQL，造成映射冲突或维护分叉。
3. 把 MyBatis 的全局运行设置 `cacheEnabled`、`logImpl` 放在 XML `<properties>` 中；应放在 `<settings>`，或使用 `mybatis.configuration.*`。
4. 同时配置 `mybatis.config-location` 和 `mybatis.configuration.*`。
5. 插入后需要数据库生成主键时，忘记核对 `useGeneratedKeys`、`keyProperty` 以及数据库表的自增规则。

参考：[MyBatis starter 配置](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/)、[MyBatis 全局配置](https://mybatis.org/mybatis-3/configuration.html)。原始资料：《数据访问》PDF，第 9—12 页。
