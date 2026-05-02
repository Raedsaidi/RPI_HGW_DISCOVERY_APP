# ─────────────────────────────────────────
#  Stage 1 — Build
# ─────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./

RUN npm install


COPY . .

ARG VITE_AUTH_URL
ARG VITE_DISCOVERY_URL
ENV VITE_AUTH_URL=$VITE_AUTH_URL
ENV VITE_DISCOVERY_URL=$VITE_DISCOVERY_URL

RUN npm run build

# ─────────────────────────────────────────
#  Stage 2 — Serve with Nginx
# ─────────────────────────────────────────
FROM nginx:1.25-alpine AS production

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/app.conf

COPY --from=builder /app/dist /usr/share/nginx/html


EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:80/health || exit 1

CMD ["nginx", "-g", "daemon off;"]