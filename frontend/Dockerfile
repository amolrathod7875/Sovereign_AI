FROM node:20-alpine

WORKDIR /app

RUN npm install -g pnpm

COPY frontend/package.json ./
RUN pnpm install

COPY frontend ./

ENV VITE_API_BASE_URL=http://backend:8000

EXPOSE 3000

CMD ["pnpm", "dev", "--host", "0.0.0.0"]
