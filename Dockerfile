FROM python:3.12-slim
WORKDIR /app

# Instalar Docker CLI + dependências
RUN apt-get update && apt-get install -y \
    gcc curl gnupg lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn python-dotenv SQLAlchemy \
    aiosqlite openai httpx groq google-genai aiofiles duckduckgo-search

COPY app/ /app/
COPY providers/ /app/providers/
COPY .env /app/.env
RUN mkdir -p /app/data
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5002", "--log-level", "warning"]
