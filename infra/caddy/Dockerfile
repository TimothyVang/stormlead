# caddy 2.8+ with coraza-caddy v2 baked in
# build: docker compose build caddy

FROM caddy:2.8-builder AS builder
RUN xcaddy build \
    --with github.com/corazawaf/coraza-caddy/v2 \
    --with github.com/hslatman/caddy-crowdsec-bouncer/http \
    --with github.com/mholt/caddy-ratelimit

FROM caddy:2.8

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# pull owasp crs at build time so we have a known version
RUN apk add --no-cache git \
    && git clone --depth 1 --branch v4.7.0 \
        https://github.com/coreruleset/coreruleset.git \
        /etc/caddy/owasp_crs \
    && apk del git

COPY Caddyfile /etc/caddy/Caddyfile
COPY coraza.conf /etc/caddy/coraza.conf
