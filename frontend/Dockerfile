FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html
COPY config.js /usr/share/nginx/html/config.js

# Phase 2B renderer-UAT prototype (isolated from the main app) and its
# vendored, no-build-step plotting libraries -- see frontend/vendor/README.md.
COPY waveform-prototype.html /usr/share/nginx/html/waveform-prototype.html
COPY vendor /usr/share/nginx/html/vendor

# Rewrites config.js from API_BASE_URL on container start.
COPY docker-entrypoint.d/10-powerwave-config.sh /docker-entrypoint.d/10-powerwave-config.sh
RUN chmod +x /docker-entrypoint.d/10-powerwave-config.sh

EXPOSE 80
