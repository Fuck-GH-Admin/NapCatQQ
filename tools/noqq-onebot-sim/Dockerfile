FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt simulator.py fixture_media.py /app/
RUN python -m pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/simulator.py"]
CMD ["--url", "ws://astrbot:6199/ws", "--allow-remote"]
