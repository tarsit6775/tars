FROM python:3.11-slim

WORKDIR /app

# Install Python deps
COPY relay/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy relay server
COPY relay/server.py .

# Copy built dashboard
COPY relay/static/ static/

EXPOSE 8420

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8420"]
