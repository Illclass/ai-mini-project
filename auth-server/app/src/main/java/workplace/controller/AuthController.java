package workplace.controller;

import com.auth0.jwt.exceptions.JWTVerificationException;
import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import workplace.model.AuthIdentity;
import workplace.model.User;
import workplace.service.AuthService;
import workplace.service.JwtService;
import workplace.service.SessionService;

@RestController
@RequestMapping("/api")
public class AuthController {
    private final AuthService auth;
    private final JwtService jwt;
    private final SessionService sessions;

    public AuthController(AuthService auth, JwtService jwt, SessionService sessions) {
        this.auth = auth;
        this.jwt = jwt;
        this.sessions = sessions;
    }

    @PostMapping(value = "/signup", consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> signUp(@RequestParam(required = false) String username,
                                    @RequestParam(required = false) String password,
                                    HttpServletRequest request) {
        auth.signUp(username, password);
        return acceptsJson(request) ? ResponseEntity.status(201).body(new Success(true))
                : ResponseEntity.status(302).location(URI.create("/login")).build();
    }

    @PostMapping(value = "/login", consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> login(@RequestParam(required = false) String username,
                                   @RequestParam(required = false) String password) {
        User user = auth.login(username, password);
        if (user == null) {
            return ResponseEntity.status(401).body(new Error(false, "invalid credentials"));
        }
        String token = jwt.createToken(user);
        String sessionId = sessions.create(user);
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie("SESSION_ID", sessionId, true, false),
                        cookie("ACCESS_TOKEN", token, true, false), cookie("APP_AUTH", "1", false, false))
                .body(new LoginResponse(true, "http://localhost:5174/", token, "Bearer", JwtService.EXPIRES_IN));
    }

    @GetMapping("/auth/check")
    public ResponseEntity<?> check(HttpServletRequest request,
                                   @CookieValue(name = "SESSION_ID", required = false) String sessionId,
                                   @CookieValue(name = "ACCESS_TOKEN", required = false) String token) {
        List<String> headers = Collections.list(request.getHeaders(HttpHeaders.AUTHORIZATION));
        if (!headers.isEmpty()) {
            // 명시한 헤더가 잘못되면 유효한 쿠키·세션으로 인증을 우회하지 않는다.
            try {
                if (headers.size() != 1) return unauthorized();
                String value = headers.get(0);
                if (!value.regionMatches(true, 0, "Bearer ", 0, 7) || value.substring(7).isBlank()) {
                    return unauthorized();
                }
                return verified("bearer", jwt.verifyToken(value.substring(7)));
            } catch (JWTVerificationException | IllegalArgumentException ex) {
                return unauthorized();
            }
        }
        AuthIdentity identity = sessions.find(sessionId);
        if (identity != null) {
            return ResponseEntity.ok(new SessionResponse(true, "session", identity.username()));
        }
        if (token != null && !token.isBlank()) {
            try {
                return verified("jwt", jwt.verifyToken(token));
            } catch (JWTVerificationException | IllegalArgumentException ex) {
                return unauthorized();
            }
        }
        return unauthorized();
    }

    @PostMapping("/logout")
    public ResponseEntity<?> logout(@CookieValue(name = "SESSION_ID", required = false) String sessionId,
                                    HttpServletRequest request) {
        sessions.remove(sessionId);
        ResponseEntity.BodyBuilder response = ResponseEntity.status(acceptsJson(request) ? 200 : 302)
                .header(HttpHeaders.SET_COOKIE, cookie("SESSION_ID", "", true, true),
                        cookie("ACCESS_TOKEN", "", true, true), cookie("APP_AUTH", "", false, true));
        return acceptsJson(request) ? response.body(new Success(true))
                : response.location(URI.create("/login")).build();
    }

    private static ResponseEntity<?> verified(String via, AuthIdentity identity) {
        return ResponseEntity.ok(new CheckResponse(true, via, identity.username(), identity.subject()));
    }

    private static ResponseEntity<?> unauthorized() {
        return ResponseEntity.status(401).header(HttpHeaders.WWW_AUTHENTICATE, "Bearer")
                .body(new Unauthorized(false, "UNAUTHORIZED"));
    }

    private static boolean acceptsJson(HttpServletRequest request) {
        String accept = request.getHeader(HttpHeaders.ACCEPT);
        return accept != null && accept.toLowerCase(Locale.ROOT).contains(MediaType.APPLICATION_JSON_VALUE);
    }

    private static String cookie(String name, String value, boolean httpOnly, boolean delete) {
        ResponseCookie.ResponseCookieBuilder cookie = ResponseCookie.from(name, value)
                .path("/").httpOnly(httpOnly).sameSite("Lax");
        if (delete) cookie.maxAge(0);
        return cookie.build().toString();
    }

    public record Success(boolean ok) {}
    public record Error(boolean ok, String error) {}
    public record Unauthorized(boolean ok, String reason) {}
    public record LoginResponse(boolean ok, String redirect, String accessToken, String tokenType, int expiresIn) {}
    public record SessionResponse(boolean ok, String via, String username) {}
    public record CheckResponse(boolean ok, String via, String username, String sub) {}
}
