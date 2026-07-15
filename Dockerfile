# NovaGuard Casino Operations — stdlib-only Python, so the image needs nothing
# beyond the interpreter itself.
FROM python:3.12-slim

WORKDIR /app
COPY casino_ops.py .

# Headless container: don't try to launch a local browser.
ENV NOVAGUARD_OPEN_BROWSER=0
ENV PORT=8000

EXPOSE 8000

# Secrets (NOVAGUARD_PANEL_USER/PASS, NOVAGUARD_API_KEY, ...) must be
# supplied at `docker run` / compose time — see docker-compose.yml.
CMD ["python", "casino_ops.py"]
