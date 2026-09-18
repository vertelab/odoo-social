FROM node:20-bookworm-slim

# node-canvas native deps (same pattern as render-engine's render-node)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      python3 \
      pkg-config \
      libcairo2-dev \
      libpango1.0-dev \
      libjpeg-dev \
      libgif-dev \
      librsvg2-dev \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY server.mjs .

ENV PORT=8600
ENV RENDER_TOKEN=change-me
ENV API_BASE_URL=http://odoo:8069

EXPOSE 8600

CMD ["node", "server.mjs"]
