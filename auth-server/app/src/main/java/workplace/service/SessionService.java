package workplace.service;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;
import workplace.model.AuthIdentity;
import workplace.model.User;

/** 기존 SESSION_ID 쿠키 호환용. 세션은 서버 재시작 시 사라진다. */
@Service
public class SessionService {
    private final Map<String, AuthIdentity> sessions = new ConcurrentHashMap<>();

    public String create(User user) {
        String id = UUID.randomUUID().toString();
        sessions.put(id, new AuthIdentity(String.valueOf(user.getId()), user.getUsername()));
        return id;
    }

    public AuthIdentity find(String id) {
        return id == null ? null : sessions.get(id);
    }

    public void remove(String id) {
        if (id != null) sessions.remove(id);
    }
}
