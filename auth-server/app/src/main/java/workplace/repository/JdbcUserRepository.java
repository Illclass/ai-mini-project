package workplace.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import workplace.model.User;

@Repository
public class JdbcUserRepository implements UserRepository {
    private final JdbcTemplate jdbc;

    public JdbcUserRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void save(User user) {
        jdbc.update("INSERT INTO users(username, password) VALUES(?, ?)",
                user.getUsername(), user.getPassword());
    }

    @Override
    public User findByUsername(String username) {
        return jdbc.query("SELECT id, username, password FROM users WHERE username = ?",
                (rs, row) -> new User(rs.getLong("id"), rs.getString("username"), rs.getString("password")),
                username).stream().findFirst().orElse(null);
    }
}
