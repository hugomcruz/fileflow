FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
RUN npm install -g serve
COPY --from=builder /app/dist /app/dist
EXPOSE 3000
# serve in SPA mode (--single) so React Router handles client-side routing
CMD ["serve", "-s", "/app/dist", "-l", "3000"]
