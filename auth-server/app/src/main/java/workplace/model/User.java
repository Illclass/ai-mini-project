package workplace.model;

/** DB 조회용 모델. 응답이나 세션에 비밀번호 해시를 포함하지 않는다. */
public class User {
    private final Long id;
    private final String username;
    private final String password;

    public User(Long id, String username, String password) {
        this.id = id;
        this.username = username;
        this.password = password;
    }

    public Long getId() { return id; }
    public String getUsername() { return username; }
    public String getPassword() { return password; }
}
