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

# Tells Next.js and its dependencies to run in production mode (faster,
# no dev-only checks).
ENV NODE_ENV=production

# Copy ONLY what's needed to run, pulled FROM the builder stage:
#   - node_modules : the installed dependencies
#   - .next        : the compiled application
#   - public       : static assets (images, etc.)
#   - the config + manifest so `npm start` works
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs

# Document that this container listens on port 3000 (Next.js default).
EXPOSE 3000

# The command that runs when the container starts: serve the built app.
CMD ["npm", "start"]
