# 如何用 Druid 管理数据库连接并监控 SQL

## Druid 提供哪些连接池与监控能力

Druid 是 JDBC 连接池，处在 DataSource 的位置。它能提供连接池指标、SQL 统计和监控组件。应用可以手动创建 `DruidDataSource`，也可以使用 Druid starter 自动配置；两条集成路径择其一。

要区分四个组件：`StatFilter` 统计 SQL，`WallFilter` 检查 SQL，`WebStatFilter` 统计 HTTP 请求，`StatViewServlet` 提供监控页面。前两者位于 SQL 层，后两者位于 Web 层。

## 通过 starter 接入 Druid 与开启统计

Spring Boot 3.x 使用 Druid 的 `druid-spring-boot-3-starter`。此处 `1.2.24` 是教学示例版本；实际项目锁定经验证的兼容版本。项目还需要 JDBC starter 和 MySQL 驱动，连接信息由 `spring.datasource.*` 提供。

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
<dependency>
  <groupId>com.alibaba</groupId>
  <artifactId>druid-spring-boot-3-starter</artifactId>
  <version>1.2.24</version>
</dependency>
```

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/student
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    druid:
      initial-size: 2
      max-active: 10
      filter:
        stat:
          enabled: true
          log-slow-sql: true
          slow-sql-millis: 2000
        wall:
          enabled: true
      stat-view-servlet:
        enabled: false
```

监控页面默认关闭；确需使用时应单独配置访问限制。若不用 starter，也能自己声明 DataSource Bean：

```java
@Configuration
public class DataSourceConfig {
    @Bean
    @ConfigurationProperties("spring.datasource")
    public DataSource dataSource() {
        return new DruidDataSource();
    }
}
```

手动方案还需分别核对属性绑定与监控组件注册；上面的 Bean 只演示 DataSource 的替换位置。

## Druid 如何接入 JDBC 与 Web 请求链

JDBC 驱动负责与 MySQL 通信，DataSource 负责提供连接，JdbcTemplate 和 MyBatis 在其上执行 SQL。Druid 替换默认连接池后，这两个上层访问 API 仍通过 DataSource 取连接。Druid 的 `WebStatFilter` 位于 Servlet 请求链；Spring MVC 的 `HandlerInterceptor` 位于 MVC handler 链，两者都不等同于 Druid 的 SQL `StatFilter`。

## 版本、过滤器开关和监控入口的误区

1. Boot 2.x 与 3.x 的 Druid starter 名称不同；旧版 1.1.x 示例不能直接搬到 Boot 3。
2. 配置慢 SQL 阈值却没有启用 `filter.stat.enabled`，就期待记录慢 SQL。
3. 把 SQL `StatFilter`、HTTP `WebStatFilter` 和监控页面当成同一个功能开关。
4. 将监控页以固定弱密码暴露；教学示例口令不能用于真实环境。
5. 认为 `WallFilter` 可代替参数化 SQL 与数据库权限控制。

参考：[Druid starter 配置](https://github.com/alibaba/druid/blob/master/druid-spring-boot-starter/README.md)、[Druid Boot 版本对应关系](https://github.com/alibaba/druid/blob/master/README.md)。原始资料：《数据访问》PDF，第 3—8 页。
