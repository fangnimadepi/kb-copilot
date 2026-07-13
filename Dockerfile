FROM python:3.11-slim

WORKDIR /srv/kb-copilot

# 依赖层单独缓存：pyproject 不变就不重装
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY app ./app
COPY static ./static

EXPOSE 8000
# api 与 worker 共用镜像，compose 里用 command 区分
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
