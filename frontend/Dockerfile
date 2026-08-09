FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html
COPY config.js /usr/share/nginx/html/config.js

# Rewrites config.js from API_BASE_URL on container start.
COPY docker-entrypoint.d/10-powerwave-config.sh /docker-entrypoint.d/10-powerwave-config.sh
RUN chmod +x /docker-entrypoint.d/10-powerwave-config.sh

EXPOSE 80
