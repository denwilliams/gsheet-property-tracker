FROM node:22-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV PORT=5713
EXPOSE 5713
CMD ["node", "build/index.js"]
