package workplace.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.DefaultCorsProcessor;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestPolicyFilter extends OncePerRequestFilter {
    private static final Logger LOG = LoggerFactory.getLogger(RequestPolicyFilter.class);
    private static final Set<String> ROUTES = Set.of("/", "/login", "/signup", "/home",
            "/api/signup", "/api/login", "/api/logout", "/api/auth/check");
    private final CorsConfiguration cors = new CorsConfiguration();
    private final DefaultCorsProcessor processor = new DefaultCorsProcessor();

    public RequestPolicyFilter() {
        List<String> origins = new ArrayList<>(List.of("http://localhost:5174", "http://127.0.0.1:5174",
                "http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:8001",
                "http://127.0.0.1:8001", "http://localhost:8008"));
        String extraOrigin = System.getenv("CHEMBRIDGE_EXTRA_ORIGIN");
        if (extraOrigin != null && !extraOrigin.isBlank()) {
            URI origin = URI.create(extraOrigin);
            if (!"http".equals(origin.getScheme())
                    || !Set.of("localhost", "127.0.0.1").contains(origin.getHost())
                    || origin.getPort() < 1 || origin.getPort() > 65535
                    || origin.getRawUserInfo() != null || !origin.getPath().isEmpty()
                    || origin.getQuery() != null || origin.getFragment() != null) {
                throw new IllegalArgumentException("Extra development origin must be an exact loopback origin");
            }
            if (!origins.contains(extraOrigin)) origins.add(extraOrigin);
        }
        cors.setAllowedOrigins(origins);
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "Authorization", "Accept"));
        cors.setAllowCredentials(true);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            if (request.getRequestURI().startsWith("/api/")) response.setHeader("Cache-Control", "no-store");
            if (!processor.processRequest(cors, request, response)) return;
            if ("OPTIONS".equals(request.getMethod())) {
                response.setStatus(204);
                return;
            }
            chain.doFilter(request, response);
        } catch (Exception ex) {
            if (!response.isCommitted()) {
                response.resetBuffer();
                response.setStatus(500);
                response.setContentType("application/json;charset=UTF-8");
                response.getWriter().write("{\"ok\":false,\"error\":\"internal server error\"}");
            }
        } finally {
            String uri = request.getRequestURI();
            String path = ROUTES.contains(uri) ? uri : uri.startsWith("/static/") ? "/static/**" : "/<unmatched>";
            LOG.info("path={} status={} latency_ms={}", path, response.getStatus(),
                    (System.nanoTime() - started) / 1_000_000.0);
        }
    }
}
