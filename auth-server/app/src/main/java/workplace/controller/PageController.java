package workplace.controller;

import java.net.URI;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.util.HtmlUtils;
import workplace.model.AuthIdentity;
import workplace.service.SessionService;

@Controller
public class PageController {
    private final SessionService sessions;

    public PageController(SessionService sessions) {
        this.sessions = sessions;
    }

    @GetMapping("/")
    public String index() { return "redirect:/login"; }

    @GetMapping("/login")
    public ResponseEntity<Resource> login() { return page("login.html"); }

    @GetMapping("/signup")
    public ResponseEntity<Resource> signup() { return page("signup.html"); }

    @GetMapping(value = "/home", produces = MediaType.TEXT_HTML_VALUE)
    public ResponseEntity<?> home(@CookieValue(name = "SESSION_ID", required = false) String sessionId) {
        AuthIdentity identity = sessions.find(sessionId);
        if (identity == null) return ResponseEntity.status(302).location(URI.create("/login")).build();
        return ResponseEntity.ok().contentType(MediaType.TEXT_HTML).body("""
                <!doctype html><html><head><meta charset="UTF-8"><title>Home</title>
                <link rel="stylesheet" href="/static/style.css"></head><body><div class="container">
                <h1>Welcome, %s</h1><form method="POST" action="/api/logout">
                <button type="submit">Logout</button></form></div></body></html>
                """.formatted(HtmlUtils.htmlEscape(identity.username())));
    }

    private static ResponseEntity<Resource> page(String name) {
        return ResponseEntity.ok().contentType(MediaType.TEXT_HTML).body(new ClassPathResource("web/" + name));
    }
}
