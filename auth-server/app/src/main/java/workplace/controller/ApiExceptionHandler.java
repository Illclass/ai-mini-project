package workplace.controller;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 내부 SQL·비밀번호·토큰을 응답이나 예외 로그에 노출하지 않는다. */
@RestControllerAdvice(assignableTypes = AuthController.class)
public class ApiExceptionHandler {
    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<?> duplicate(HttpServletRequest request) {
        return error(400, "username already exists", request);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<?> invalidInput(HttpServletRequest request) {
        return error(400, "username and password are required", request);
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<?> databaseError(HttpServletRequest request) {
        return error(500, request.getRequestURI().equals("/api/signup") ? "signup error" : "login error", request);
    }

    private static ResponseEntity<?> error(int status, String message, HttpServletRequest request) {
        if (request.getRequestURI().equals("/api/signup")) {
            return ResponseEntity.status(status).contentType(MediaType.TEXT_PLAIN).body(message);
        }
        return ResponseEntity.status(status).body(new AuthController.Error(false, message));
    }
}
