FROM python:3.12-slim-bookworm
WORKDIR /bridge
COPY integrations/he_mcp/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Shared pure Pydantic DTOs only; the bridge has no HE database/runtime package.
COPY backend/app/assistant/schemas.py ./app/assistant/schemas.py
COPY integrations/he_mcp/__init__.py integrations/he_mcp/client.py integrations/he_mcp/server.py ./integrations/he_mcp/
ENV PYTHONPATH=/bridge PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
EXPOSE 8020
CMD ["uvicorn","integrations.he_mcp.server:app","--host","0.0.0.0","--port","8020","--no-access-log"]
