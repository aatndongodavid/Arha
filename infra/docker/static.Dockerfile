# Builds the three front ends and ships them inside the Caddy image (non root).
FROM node:25-bookworm-slim AS build
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json ./
COPY packages packages
COPY apps/web apps/web
COPY apps/forms apps/forms
COPY apps/site apps/site
COPY config config
ARG ARHA_APP_URL
ARG ARHA_API_URL
ARG ARHA_SITE_URL
ENV ARHA_APP_URL=$ARHA_APP_URL ARHA_API_URL=$ARHA_API_URL ARHA_SITE_URL=$ARHA_SITE_URL
RUN pnpm install --frozen-lockfile && pnpm --filter @arha/forms build && pnpm --filter @arha/web build && pnpm --filter @arha/site build

FROM caddy:2-alpine
COPY --from=build /repo/apps/web/dist /srv/web
COPY --from=build /repo/apps/forms/dist /srv/forms
COPY --from=build /repo/apps/site/dist /srv/site
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
USER 1000
