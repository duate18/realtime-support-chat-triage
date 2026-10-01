FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Prima le dipendenze: finché requirements.txt non cambia, Docker riusa questo passaggio dalla cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY scripts scripts
COPY data data

# Il modello viene addestrato durante la build, così dentro l'immagine c'è sempre
# la versione di scikit-learn che lo ha creato.
RUN python -m scripts.train

# Il server gira con un utente senza privilegi, non come root.
RUN useradd --create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
