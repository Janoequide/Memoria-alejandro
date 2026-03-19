FROM node:18
WORKDIR /app
COPY package*.json package-lock.json ./
RUN npm install
COPY . .
ARG NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]