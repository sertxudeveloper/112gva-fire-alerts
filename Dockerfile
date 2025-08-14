FROM python:3.13-trixie

WORKDIR /app

ADD requirements.txt .

RUN pip install -r requirements.txt \
    && rm -rf /root/.cache

ADD . /app

CMD ["python", "./main.py"]
