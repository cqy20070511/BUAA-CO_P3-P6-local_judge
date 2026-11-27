FROM eclipse-temurin:8-jre-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    ALLOW_SOURCE_PATH=0

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-minimal curl ca-certificates gnupg xz-utils \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# P5 / P6 的测试点不入 Git，构建镜像时生成；P3 / P4 的测试点随仓库。
RUN python3 prepare_data.py

EXPOSE 10000
CMD ["python3", "server.py"]
