# Build the web app, then serve it with nginx, which also forwards /v1 to AppJs Studio's API.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# Runtime settings, from the container's environment:
#   APP_KEY     the Studio app key of restyle-ai (written into /config.js at start)
#   STUDIO_API  where /v1 goes (default: the api service of Studio's compose stack)
ENV APP_KEY="" STUDIO_API="http://api:8000"
COPY docker/default.conf.template /etc/nginx/templates/default.conf.template
COPY docker/40-restyle-config.sh /docker-entrypoint.d/40-restyle-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.d/40-restyle-config.sh
EXPOSE 80
