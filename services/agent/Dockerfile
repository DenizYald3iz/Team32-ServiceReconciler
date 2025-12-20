FROM node:18-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 8070
CMD ["node","--no-warnings","--unhandled-rejections=strict","index.js"]
