FROM python:3.10.8-alpine

WORKDIR /app

COPY ./src/ /app

RUN useradd -u 1000 -m bot

USER bot
RUN pip3 install -r requirements.txt

EXPOSE 8080
HEALTHCHECK  --interval=5m --timeout=3s --start-period=15s \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/livez || exit 1

ENTRYPOINT [ "/app/bot.py" ]
