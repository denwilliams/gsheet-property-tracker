FROM python:3.12-slim

WORKDIR /app

RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml
RUN playwright install chromium --with-deps

COPY scraper/ scraper/
CMD ["python", "-m", "scraper.main"]
