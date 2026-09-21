FROM python:3.12-slim

# Pinned versions, so the image matches what was tested.
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY app.py booking.py intake.py ./
COPY static/ ./static/

# The app writes appointments.sqlite3 next to itself and chmods it to 0600,
# so the runtime user has to own this directory.
RUN useradd --create-home --uid 1000 jannet && chown -R jannet:jannet /app
USER jannet

# Hugging Face Spaces serves 7860; Render, Railway and Cloud Run inject $PORT.
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
