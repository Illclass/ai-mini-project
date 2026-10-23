package workplace;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTCreator;
import com.auth0.jwt.algorithms.Algorithm;
import jakarta.servlet.http.Cookie;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mindrot.jbcrypt.BCrypt;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import workplace.model.User;
import workplace.repository.UserRepository;
import workplace.service.JwtService;
import workplace.service.SessionService;

@SpringBootTest(properties = "spring.autoconfigure.exclude=org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration")
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class AuthApiTest {
    private static final String SECRET = UUID.randomUUID().toString();
    private static final String PASSWORD = UUID.randomUUID().toString();
    private static final String HASH = BCrypt.hashpw(PASSWORD, BCrypt.gensalt(4));
    private final User user = new User(42L, "mvc-user", HASH);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add("JWT_SECRET", () -> SECRET);
    }

    @Autowired MockMvc mvc;
    @Autowired JwtService jwt;
    @Autowired SessionService sessions;
    @MockitoBean UserRepository users;

    @BeforeEach
    void setup() { when(users.findByUsername("mvc-user")).thenReturn(user); }

    @Test
    void signupStoresOnlyBcryptAndReturnsSwaggerJson() throws Exception {
        doAnswer(invocation -> {
            User saved = invocation.getArgument(0);
            assertThat(saved.getUsername()).isEqualTo("new-user");
            assertThat(saved.getPassword()).startsWith("$2a$12$").isNotEqualTo(PASSWORD);
            assertThat(BCrypt.checkpw(PASSWORD, saved.getPassword())).isTrue();
            return null;
        }).when(users).save(any());
        mvc.perform(post("/api/signup").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .accept(MediaType.APPLICATION_JSON).param("username", " new-user ").param("password", PASSWORD))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.ok").value(true))
                .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
        verify(users).save(any());
    }

    @Test
    void formSignupKeepsLoginRedirect() throws Exception {
        mvc.perform(post("/api/signup").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "new-user").param("password", PASSWORD))
                .andExpect(status().isFound()).andExpect(header().string(HttpHeaders.LOCATION, "/login"));
    }

    @Test
    void duplicateUsernameReturns400IncludingConcurrentInsert() throws Exception {
        mvc.perform(post("/api/signup").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "mvc-user").param("password", PASSWORD))
                .andExpect(status().isBadRequest()).andExpect(content().string("username already exists"));
        doThrow(new DuplicateKeyException("private SQL details")).when(users).save(any());
        mvc.perform(post("/api/signup").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "new-user").param("password", PASSWORD))
                .andExpect(status().isBadRequest()).andExpect(content().string("username already exists"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"/api/signup", "/api/login"})
    void missingCredentialsAre400(String path) throws Exception {
        mvc.perform(post(path).contentType(MediaType.APPLICATION_FORM_URLENCODED))
                .andExpect(status().isBadRequest());
    }

    @Test
    void loginIssuesCompatibleJwtCookiesAndCopyableBearer() throws Exception {
        var result = mvc.perform(post("/api/login").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "mvc-user").param("password", PASSWORD))
                .andExpect(status().isOk()).andExpect(jsonPath("$.ok").value(true))
                .andExpect(jsonPath("$.redirect").value("http://localhost:5174/"))
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.expiresIn").value(3600))
                .andExpect(jsonPath("$.accessToken").isString())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().doesNotExist(HttpHeaders.LOCATION)).andReturn();
        var response = result.getResponse();
        String token = response.getCookie("ACCESS_TOKEN").getValue();
        assertThat(response.getContentAsString()).contains(token).doesNotContain(HASH, PASSWORD);
        assertThat(jwt.verifyToken(token).subject()).isEqualTo("42");
        var decoded = JWT.decode(token);
        assertThat(decoded.getIssuer()).isEqualTo("simple-auth-server");
        assertThat(decoded.getExpiresAt().getTime() - decoded.getIssuedAt().getTime()).isEqualTo(3_600_000L);
        assertThat(response.getCookie("SESSION_ID").isHttpOnly()).isTrue();
        assertThat(response.getCookie("ACCESS_TOKEN").isHttpOnly()).isTrue();
        assertThat(response.getCookie("APP_AUTH").isHttpOnly()).isFalse();
        assertThat(response.getHeaders(HttpHeaders.SET_COOKIE)).allMatch(value -> value.contains("SameSite=Lax"));
        mvc.perform(get("/api/auth/check").header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.via").value("bearer"))
                .andExpect(jsonPath("$.sub").value("42"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"unknown-user", "mvc-user"})
    void incorrectCredentialsAre401(String name) throws Exception {
        mvc.perform(post("/api/login").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", name).param("password", "incorrect-password"))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.error").value("invalid credentials"));
    }

    @Test
    void missingAuthenticationIs401AndCookieCompatibilityWorks() throws Exception {
        mvc.perform(get("/api/auth/check")).andExpect(status().isUnauthorized())
                .andExpect(header().string(HttpHeaders.WWW_AUTHENTICATE, "Bearer"));
        mvc.perform(get("/api/auth/check").cookie(new Cookie("SESSION_ID", sessions.create(user))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.via").value("session"));
        mvc.perform(get("/api/auth/check").cookie(new Cookie("ACCESS_TOKEN", jwt.createToken(user))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.via").value("jwt"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"Bearer invalid", "Basic invalid", "", "Bearer "})
    void invalidExplicitHeaderCannotFallBackToCookies(String authorization) throws Exception {
        mvc.perform(get("/api/auth/check").header(HttpHeaders.AUTHORIZATION, authorization)
                        .cookie(new Cookie("SESSION_ID", sessions.create(user)),
                                new Cookie("ACCESS_TOKEN", jwt.createToken(user))))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void multipleAuthorizationHeadersAreRejected() throws Exception {
        mvc.perform(get("/api/auth/check").header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + jwt.createToken(user), "Bearer invalid"))
                .andExpect(status().isUnauthorized());
    }

    @ParameterizedTest
    @ValueSource(strings = {"expired", "wrong-issuer", "no-exp", "no-sub", "blank-sub", "bad-signature"})
    void invalidJwtClaimsOrSignatureAre401(String kind) throws Exception {
        JWTCreator.Builder builder = JWT.create().withIssuer(kind.equals("wrong-issuer") ? "other" : "simple-auth-server");
        if (!kind.equals("no-exp")) builder.withExpiresAt(Date.from(Instant.now().plusSeconds(kind.equals("expired") ? -60 : 60)));
        if (!kind.equals("no-sub")) builder.withSubject(kind.equals("blank-sub") ? " " : "42");
        String token = builder.sign(Algorithm.HMAC256(kind.equals("bad-signature") ? UUID.randomUUID().toString() : SECRET));
        mvc.perform(get("/api/auth/check").header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logoutRemovesSessionAndAllCookiesButBearerRemainsValidUntilExpiry() throws Exception {
        String id = sessions.create(user);
        String token = jwt.createToken(user);
        var response = mvc.perform(post("/api/logout").accept(MediaType.APPLICATION_JSON)
                        .cookie(new Cookie("SESSION_ID", id)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.ok").value(true)).andReturn().getResponse();
        assertThat(sessions.find(id)).isNull();
        assertThat(response.getHeaders(HttpHeaders.SET_COOKIE)).hasSize(3)
                .allMatch(value -> value.contains("Max-Age=0") && value.contains("Path=/"));
        mvc.perform(get("/api/auth/check").cookie(new Cookie("SESSION_ID", id))).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/auth/check").header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isOk());
        mvc.perform(post("/api/logout")).andExpect(status().isFound())
                .andExpect(header().string(HttpHeaders.LOCATION, "/login"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:8001",
            "http://127.0.0.1:8001", "http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:8008"})
    void allowedOriginsSupportUnauthenticatedPreflightAndCorsOnErrors(String origin) throws Exception {
        mvc.perform(options("/api/login").header(HttpHeaders.ORIGIN, origin)
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization,content-type"))
                .andExpect(status().isNoContent()).andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin))
                .andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
        mvc.perform(get("/api/auth/check").header(HttpHeaders.ORIGIN, origin))
                .andExpect(status().isUnauthorized()).andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin));
    }

    @Test
    void forbiddenOriginMethodAndHeaderAreRejectedBeforeSignup() throws Exception {
        mvc.perform(post("/api/signup").contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .header(HttpHeaders.ORIGIN, "https://untrusted.example")
                        .param("username", "new-user").param("password", PASSWORD))
                .andExpect(status().isForbidden());
        mvc.perform(options("/api/login").header(HttpHeaders.ORIGIN, "http://localhost:8001")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
                .andExpect(status().isForbidden());
        mvc.perform(options("/api/login").header(HttpHeaders.ORIGIN, "http://localhost:8001")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "X-Unapproved-Header"))
                .andExpect(status().isForbidden());
    }

    @Test
    void pagesAndStaticAssetsRemainAvailableAndHomeEscapesUsername() throws Exception {
        mvc.perform(get("/")).andExpect(status().isFound()).andExpect(header().string(HttpHeaders.LOCATION, "/login"));
        mvc.perform(get("/login")).andExpect(status().isOk()).andExpect(content().string(org.hamcrest.Matchers.containsString("loginForm")));
        mvc.perform(get("/signup")).andExpect(status().isOk());
        mvc.perform(get("/static/style.css")).andExpect(status().isOk());
        mvc.perform(get("/home")).andExpect(status().isFound());
        String id = sessions.create(new User(5L, "<script>unsafe</script>", HASH));
        mvc.perform(get("/home").cookie(new Cookie("SESSION_ID", id))).andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString("&lt;script&gt;")));
    }

    @Test
    void databaseFailureAndRequestLogsDoNotExposePrivateData(CapturedOutput output) throws Exception {
        String sensitive = "private-sql-" + UUID.randomUUID();
        when(users.findByUsername(anyString())).thenThrow(new DataAccessResourceFailureException(sensitive));
        mvc.perform(post("/api/login").queryParam("private", sensitive)
                        .header(HttpHeaders.ORIGIN, "http://localhost:8001")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + sensitive)
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "mvc-user").param("password", PASSWORD))
                .andExpect(status().isInternalServerError()).andExpect(jsonPath("$.error").value("login error"))
                .andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, "http://localhost:8001"));
        assertThat(output.getOut()).contains("path=/api/login status=500 latency_ms=")
                .doesNotContain(sensitive, PASSWORD, HASH);
        assertThat(output.getErr()).doesNotContain(sensitive, PASSWORD, HASH);
    }
}
