package workplace.repository;

import workplace.model.User;

public interface UserRepository {
    void save(User user);
    User findByUsername(String username);
}
