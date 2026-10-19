#!/bin/sh
set -eu
set -f

# Preserve the space-separated list used by existing Compose deployments.
{
    for proxy in ${TRUSTED_PROXIES:-127.0.0.1 172.31.210.1}; do
        printf 'set_real_ip_from %s;\n' "$proxy"
    done
    printf 'real_ip_header X-Forwarded-For;\nreal_ip_recursive on;\n'
} > /etc/nginx/conf.d/real-ip.conf
