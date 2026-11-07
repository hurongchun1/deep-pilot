# Lettuce 与 Jedis 在 Spring Boot 中如何切换

## Lettuce 与 Jedis 位于哪一层

Lettuce 和 Jedis 是连接 Redis 的 Java 客户端。Spring Boot Redis starter 默认带入 Lettuce；应用层仍通过 `RedisConnectionFactory`、`StringRedisTemplate` 或 `RedisTemplate` 操作 Redis。更换客户端通常不需要重写 Template 调用代码。

## 从默认 Lettuce 切换到 Jedis

默认 Lettuce 不需要额外步骤；使用 `spring-boot-starter-data-redis` 并配置 `spring.data.redis.*` 即可。若项目确定要用 Jedis，先排除 starter 自带的 Lettuce，再加入 Jedis：

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-redis</artifactId>
  <exclusions>
    <exclusion>
      <groupId>io.lettuce</groupId>
      <artifactId>lettuce-core</artifactId>
    </exclusion>
  </exclusions>
</dependency>
<dependency>
  <groupId>redis.clients</groupId>
  <artifactId>jedis</artifactId>
</dependency>
```

Boot parent 或 BOM 管理 Jedis 版本。Spring Boot 3.3 配置示例：

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      client-type: jedis
```

切换后启动应用，确认 `RedisConnectionFactory` 的实际实现，并用一条 `StringRedisTemplate` 读写验证连接。

## 更换客户端对 RedisTemplate 有何影响

应用通常通过 `StringRedisTemplate` 或 `RedisTemplate` 调用 Redis；它们依赖 `RedisConnectionFactory`，连接工厂再使用 Lettuce 或 Jedis 客户端。切换客户端改变的是连接层，通常不改变上层 Template 读写代码。这个位置类似 JDBC 场景中替换连接池，但 Redis 连接工厂与 JDBC DataSource 互不相通。

## 依赖排除与客户端配置的常见问题

1. 只写 `client-type: jedis`，却没有 Jedis 依赖。
2. 只加 Jedis 依赖，却没有按官方步骤排除 Lettuce；客户端选择可能与预期不同。
3. 将 Boot 2.x 的 `spring.redis.client-type` 复制到 Boot 3.3；应使用 `spring.data.redis.client-type`。
4. 更换客户端后不做连接读写验证，就认为配置成功。

参考：[Spring Boot：Use Jedis Instead of Lettuce](https://docs.spring.io/spring-boot/how-to/nosql.html)、[Spring Boot 3.3 Redis 配置](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)。原始资料：《数据访问》PDF，第 13—14 页。
