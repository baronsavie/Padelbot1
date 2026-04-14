FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir requests beautifulsoup4

COPY padel_bot.py /app/
COPY run.sh /app/run.sh
RUN chmod a+x /app/run.sh

CMD ["/bin/bash", "/app/run.sh"]
