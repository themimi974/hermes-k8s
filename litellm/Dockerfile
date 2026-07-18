FROM python:3.11-slim
RUN pip install --no-cache-dir "litellm[proxy]" prisma
EXPOSE 4000
ENTRYPOINT ["litellm"]
