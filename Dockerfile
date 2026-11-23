FROM nginx:alpine

RUN apk add --no-cache python3

WORKDIR /app

COPY build.py template.html container.py ./
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8000

ENTRYPOINT ["python3", "/app/container.py"]
CMD []
