# Spring Boot 如何配置 Redis 并使用 Template 读写

## Redis starter 自动提供哪些访问对象

Spring Boot 的 Redis starter 装配 Redis 客户端、`RedisConnectionFactory` 和数据操作模板。`RedisTemplate` 支持多种键和值类型；`StringRedisTemplate` 专门处理字符串，序列化配置更直接。Redis 连接链独立于 JDBC DataSource。

## 配置连接并通过 StringRedisTemplate 读写

在已有 Spring Boot 3.3 项目中引入 Redis starter，默认客户端为 Lettuce：

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      password: ${REDIS_PASSWORD:}
```

简单字符串读写可注入 `StringRedisTemplate`，为缓存值明确设置过期时间：

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GreetingStore {
    private final StringRedisTemplate redis;

    public GreetingStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String value) {
        redis.opsForValue().set("greeting", value, Duration.ofMinutes(10));
    }

    public String read() {
        return redis.opsForValue().get("greeting");
    }
}
```

复杂对象需要决定键和值如何序列化，并让写入方和读取方使用兼容的规则。可先用 `StringRedisTemplate` 存 JSON 字符串，再按项目约定处理对象映射。

## Redis 访问链与 JDBC 访问链的关系

Redis starter 与 JDBC/MyBatis starter 都遵循“依赖进入 classpath → 条件满足 → 自动配置 Bean → 注入 API 使用”的路径。但 Redis 使用自己的 `RedisConnectionFactory`，不共享 MySQL DataSource。`StringRedisTemplate` 在连接工厂之上操作数据；默认 Lettuce 客户端也可以按项目需要换成 Jedis，Template 的调用方式通常不变。

## 配置前缀、序列化与过期时间的误区

1. 把 Boot 2.x 常见的 `spring.redis.*` 配置原样用于 Boot 3.3；这里使用 `spring.data.redis.*`。
2. 以为 `RedisTemplate<Object,Object>` 的默认序列化一定生成可读字符串；与 `StringRedisTemplate` 不同。
3. 只在测试里验证 `set/get`，用于缓存时却没有设计 TTL 和失效策略。
4. Redis 服务未运行或连接凭据错误，却把连接失败归因于 Template API。

参考：[Spring Boot 3.3 Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)、[StringRedisTemplate API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/StringRedisTemplate.html)。原始资料：《数据访问》PDF，第 12—13 页。
