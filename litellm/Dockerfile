FROM ghcr.io/berriai/litellm:main-v1.69.0-stable

RUN apk update && \
    apk add --no-cache curl
    

# Copy the UI source into the container
COPY ./litellm/config.yaml /app/config.yaml

# Expose the necessary port
EXPOSE 4000/tcp

# Override the CMD instruction with your desired command and arguments
CMD ["--port", "4000", "--config", "/app/config.yaml"]