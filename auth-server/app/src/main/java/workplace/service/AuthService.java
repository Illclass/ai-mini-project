package workplace.service;

import org.mindrot.jbcrypt.BCrypt;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import workplace.model.User;
import workplace.repository.UserRepository;

@Service
public class AuthService {
    private final UserRepository userRepository;

    public AuthService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public void signUp(String username, String rawPassword) {
        username = normalize(username);
        rawPassword = normalize(rawPassword);
        validate(username, rawPassword);
        if (userRepository.findByUsername(username) != null) {
            throw new DuplicateKeyException("username already exists");
        }
        userRepository.save(new User(null, username, BCrypt.hashpw(rawPassword, BCrypt.gensalt(12))));
    }

    public User login(String username, String rawPassword) {
        username = normalize(username);
        rawPassword = normalize(rawPassword);
        validate(username, rawPassword);
        User user = userRepository.findByUsername(username);
        return user != null && BCrypt.checkpw(rawPassword, user.getPassword()) ? user : null;
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim();
    }

    private static void validate(String username, String password) {
        if (username.isBlank() || password.isBlank()) {
            throw new IllegalArgumentException("username and password are required");
        }
    }
}
