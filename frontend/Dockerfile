# syntax=docker/dockerfile:1

# MERIDIAN UI as a container: build the static export, serve it with nginx.
#
# NEXT_PUBLIC_* values are compiled into the JavaScript bundle at build time,
# so they are build args, not runtime env. The API URL is called by the
# *browser*, so it must be reachable from the user's machine (the compose
# default http://localhost:8000 is the backend's published port), not a
# container-network name like http://backend:8000.
#
#   docker build -t meridian-frontend --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 .

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Dependencies first so this layer is reused until the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_CARTO_KEY=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_CARTO_KEY=${NEXT_PUBLIC_CARTO_KEY}
RUN npm run build

# Unprivileged nginx: runs as a non-root user and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/out /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ > /dev/null || exit 1
