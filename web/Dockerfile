# DOCex frontend (Next.js) container.
#
# This is a MULTI-STAGE build. Stage 1 ("builder") has all the tools needed
# to compile the app. Stage 2 ("runner") is a clean, smaller image that only
# carries what's needed to RUN the compiled app. The build tools never ship
# to production — smaller image, smaller attack surface.
#
# Build:  docker build -t docex-web ./web
# Run:    docker run -p 3000:3000 docex-web

# ---- Stage 1: build the app ----------------------------------------------
FROM node:20-alpine AS builder

# All work happens in /app inside the container.
WORKDIR /app

# Copy ONLY the dependency manifests first, then install. Why before the rest
# of the code? Docker caches each layer. As long as these two files don't
# change, Docker reuses the cached "npm ci" layer and skips re-downloading
# every dependency — turning a 2-minute step into 0 seconds on most rebuilds.
COPY package.json package-lock.json ./
RUN npm ci

# Now copy the rest of the source and build it.
COPY . .
RUN npm run build

# ---- Stage 2: run the app -------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

# Production mode: faster, skips dev-only checks.
ENV NODE_ENV=production
# The standalone server reads these. HOSTNAME=0.0.0.0 binds to all network
# interfaces so the container is reachable from outside (not just localhost
# inside the container).
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Standalone output gives us a minimal self-contained server. We copy three
# things FROM the builder:
#   - .next/standalone : the trimmed server + only the deps it actually needs
#   - .next/static     : compiled JS/CSS (standalone does NOT bundle these)
#   - public           : static assets like images (also not auto-included)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

# Standalone emits a plain Node entrypoint (server.js) — run it directly.
# No npm, no next CLI needed in the final image.
CMD ["node", "server.js"]
