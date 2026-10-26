FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /src
COPY auth-server/ ./
RUN chmod +x gradlew && ./gradlew :app:bootJar --no-daemon --no-configuration-cache
FROM eclipse-temurin:17-jre-jammy
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/app/build/libs/*-SNAPSHOT.jar /app/auth.jar
ENTRYPOINT ["java", "-jar", "/app/auth.jar"]
