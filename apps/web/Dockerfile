FROM node:22-alpine AS deps
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @umkm/web...

FROM node:22-alpine AS builder
WORKDIR /workspace
RUN corepack enable
COPY --from=deps /workspace/node_modules ./node_modules
COPY --from=deps /workspace/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web ./apps/web
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm --filter @umkm/web build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /workspace/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /workspace/apps/web/.next/static ./apps/web/.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
