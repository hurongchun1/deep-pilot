# Servlet、MVC 与 Druid 的 Filter 各在何处生效

## 三类拦截机制分别在哪里生效

Servlet Filter 在 Servlet 过滤器链中处理请求和响应；Spring MVC Interceptor 围绕 MVC handler 执行，可在进入 Controller 前后参与处理。两者都能做一部分横切工作，但作用位置和可见的上下文不同。理解这条链有助于判断监控、日志和鉴权代码该放在哪里。

另一个容易混淆的名字是 Druid Filter：`StatFilter`、`WallFilter` 位于 SQL/连接池层，处理的是数据库语句，不是 HTTP 请求。Druid 的 `WebStatFilter` 才位于 Web 请求链。

## 注册 Servlet Filter 与 MVC Interceptor

以下示例假定 Spring Boot 3.x 项目已引入 `spring-boot-starter-web`。Servlet Filter 可以作为 Bean 注册；下面只给 `/api/*` 请求加一个响应头：

```java
@Bean
FilterRegistrationBean<Filter> apiFilter() {
    Filter filter = (request, response, chain) -> {
        ((HttpServletResponse) response).setHeader("X-App", "demo");
        chain.doFilter(request, response);
    };
    FilterRegistrationBean<Filter> registration = new FilterRegistrationBean<>(filter);
    registration.addUrlPatterns("/api/*");
    return registration;
}
```

Spring MVC Interceptor 通过 `WebMvcConfigurer` 注册到 handler 路径：

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request,
                                     HttpServletResponse response,
                                     Object handler) {
                return true;
            }
        }).addPathPatterns("/api/**");
    }
}
```

上面都是片段，需补充 `jakarta.servlet` 与 Spring MVC 相关 import。Druid 的 SQL Filter 不通过这些 Web 注册方式开启；它需要与 Boot 版本匹配的 Druid starter（Boot 3.x 对应 `druid-spring-boot-3-starter`），再通过数据源配置启用，例如：

```yaml
spring:
  datasource:
    druid:
      filter:
        stat:
          enabled: true
```

## Web 请求如何通向数据访问层

这篇与数据访问主线的交点是 Druid：它既有 SQL 层的 `StatFilter`、`WallFilter`，也有 Web 层的 `WebStatFilter`。在链路上，Web Filter/Interceptor 处理 HTTP 请求；Controller/Service 随后通过 JdbcTemplate、MyBatis 或 Redis API 访问数据。

## 同名 Filter 与拦截范围的误区

1. 看到名称都叫 Filter，就把 Druid SQL Filter 当成 Servlet Filter 注册。
2. 认为 Interceptor 覆盖全部 Servlet 请求；它围绕 Spring MVC handler 工作，范围取决于 MVC 映射。
3. 在 Filter 中忘记调用 `chain.doFilter`，导致请求无法继续。
4. 把“Filter 不依赖 Spring、Interceptor 可使用 Spring 注入”当成绝对规则；具体能力还取决于注册方式和容器管理。做安全鉴权时应使用适合的安全框架和过滤器链。

参考：[Spring Framework：MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html)、[Spring Framework：Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)。原始资料：《数据访问》PDF，第 14 页。
