package workplace.service;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import java.time.Instant;
import java.util.Date;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import workplace.model.AuthIdentity;
import workplace.model.User;

@Service
public class JwtService {
    public static final int EXPIRES_IN = 3600;
    private static final String ISSUER = "simple-auth-server";
    private final Algorithm algorithm;
    private final JWTVerifier verifier;

    public JwtService(@Value("${JWT_SECRET}") String secret) {
        if (secret == null || secret.isBlank()) {
            throw new IllegalArgumentException("JWT_SECRET must be configured");
        }
        algorithm = Algorithm.HMAC256(secret);
        verifier = JWT.require(algorithm).withIssuer(ISSUER).build();
    }

    public String createToken(User user) {
        Instant now = Instant.now();
        return JWT.create().withIssuer(ISSUER).withIssuedAt(Date.from(now))
                .withExpiresAt(Date.from(now.plusSeconds(EXPIRES_IN)))
                .withSubject(String.valueOf(user.getId())).withClaim("username", user.getUsername())
                .sign(algorithm);
    }

    public AuthIdentity verifyToken(String token) {
        DecodedJWT decoded = verifier.verify(token);
        if (decoded.getExpiresAt() == null || decoded.getSubject() == null || decoded.getSubject().isBlank()) {
            throw new JWTVerificationException("Required claims missing");
        }
        return new AuthIdentity(decoded.getSubject(), decoded.getClaim("username").asString());
    }
}
