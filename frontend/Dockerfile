# syntax=docker/dockerfile:1

# ---- build: compile the TypeScript/React bundle ----
FROM node:22-alpine AS builder

WORKDIR /build
ENV CI=1

RUN corepack enable

# Lockfile first so `pnpm install` is cached independently of source edits.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# ---- runtime: static files only, served as a non-root user ----
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

# nginx:alpine runs as root by default; bind an unprivileged port instead and
# move the pid file somewhere the nginx user can write.
RUN sed -i 's,/var/run/nginx.pid,/tmp/nginx.pid,' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx \
    && touch /tmp/nginx.pid \
    && chown nginx:nginx /tmp/nginx.pid

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
