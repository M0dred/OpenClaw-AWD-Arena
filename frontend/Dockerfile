# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Set API base to empty so it uses relative paths for Nginx proxy
ENV VITE_API_BASE=""

# Build the app
RUN npm run build

# Serve stage
FROM nginx:alpine

RUN apk add --no-cache tzdata

ARG TZ=UTC
ENV TZ=${TZ}

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
