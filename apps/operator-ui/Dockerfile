# Static build of the operator UI, served by nginx. Build context must be
# the repo root, e.g.:
#   docker build -f apps/operator-ui/Dockerfile \
#     --build-arg VITE_SIGNALING_URL=wss://teleop.example.com/ws \
#     -t teleop-operator-ui .
FROM node:22-slim AS build

WORKDIR /repo

COPY package.json package-lock.json ./
COPY shared/types shared/types
COPY apps/operator-ui apps/operator-ui

RUN npm install

ARG VITE_SIGNALING_URL=ws://localhost:8080/ws
ENV VITE_SIGNALING_URL=$VITE_SIGNALING_URL

RUN npm run build -w operator-ui

FROM nginx:alpine

COPY --from=build /repo/apps/operator-ui/dist /usr/share/nginx/html
COPY apps/operator-ui/deploy/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
