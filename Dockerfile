FROM python:3.12.9-slim

WORKDIR /app

# 先装 CPU 版 torch（PyPI 默认的 torch 是 CUDA 版，会拖入大量 nvidia 依赖撑爆镜像；本机无 CUDA 用 CPU 版）
RUN pip install --no-cache-dir torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu --timeout 300

# 再装其余依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 -r requirements.txt

# 复制项目（.env.local 一并进入，config 直接读取）
COPY . .

# git 用于二期 git clone 输入（放最后，避免破坏依赖层缓存）
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

EXPOSE 8001

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
