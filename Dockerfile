FROM python:3.10.8-alpine

WORKDIR /app

COPY ./src/ /app

RUN adduser -u 1000 --disabled-password bot

USER bot
RUN pip3 install -r requirements.txt

ENTRYPOINT [ "/app/bot.py" ]
