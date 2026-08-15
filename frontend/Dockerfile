FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html
COPY config.js /usr/share/nginx/html/config.js

# Shared Light/Dark appearance tokens + preference logic -- used by every
# page below (see docs/project-memory/DECISIONS.md DEC-023).
COPY theme.css /usr/share/nginx/html/theme.css
COPY theme.js /usr/share/nginx/html/theme.js

# Single-channel waveform preview (isolated from the main app) and its
# vendored, no-build-step Plotly.js bundle -- see frontend/vendor/README.md.
COPY waveform-prototype.html /usr/share/nginx/html/waveform-prototype.html
COPY vendor /usr/share/nginx/html/vendor

# Rewrites config.js from API_BASE_URL on container start.
COPY docker-entrypoint.d/10-powerwave-config.sh /docker-entrypoint.d/10-powerwave-config.sh
RUN chmod +x /docker-entrypoint.d/10-powerwave-config.sh

EXPOSE 80
