# syntax=docker/dockerfile:1
# Frontend build + nginx in one image. Build context is the repository root:
#   docker build -f infra/web.Dockerfile -t video-digest-web:<sha> .
# The Vite config aliases ../n8n/fixtures and `tsc -b` covers e2e/, so the whole frontend/ tree and the
# fixtures are needed at build time even though the production bundle drops the mock.

FROM node:24-alpine AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY n8n/fixtures /src/n8n/fixtures
COPY frontend/ ./
# Cloudflare Turnstile site key (public, per environment): Vite inlines VITE_* at build time, so it must be in
# the build environment – deploy.sh passes it from the .env of the app root. Empty: no widget, the server logs
# turnstile_missing on every job (step E3). Not the test key from .env.development, which only the mock uses.
ARG VITE_TURNSTILE_SITE_KEY=
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
RUN npm run build

FROM nginx:1.28-alpine AS runtime
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/frontend/dist /usr/share/nginx/html
# The mock API data is for the dev server and Playwright only.
RUN rm -rf /usr/share/nginx/html/mock
EXPOSE 80
