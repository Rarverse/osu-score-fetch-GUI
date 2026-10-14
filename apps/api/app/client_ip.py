import ipaddress


def client_ip(peer: str | None, forwarded_for: str | None, trusted: str) -> str:
    """Return the visitor address, ignoring X-Forwarded-For from anyone else.

    Matches uvicorn's proxy-header walk: only a trusted peer may supply the
    header, and the client is the rightmost address that is not itself trusted.
    """
    if not peer:
        peer = "unknown"
    hosts = _TrustedHosts(trusted)
    if peer not in hosts or not forwarded_for or not forwarded_for.strip():
        return peer
    parts = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    if not parts:
        return peer
    if hosts.always:
        return _host_only(parts[0])
    for item in reversed(parts):
        host = _host_only(item)
        if host not in hosts:
            return host
    return _host_only(parts[0])


def _host_only(value: str) -> str:
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return value
        return value[1:end]
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            return host
    return value


class _TrustedHosts:
    def __init__(self, raw: str) -> None:
        self.always = raw.strip() == "*"
        self.addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        self.networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()
        self.literals: set[str] = set()
        if self.always:
            return
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            if "/" in item:
                try:
                    self.networks.add(ipaddress.ip_network(item, strict=False))
                except ValueError:
                    self.literals.add(item)
                continue
            try:
                self.addresses.add(ipaddress.ip_address(item))
            except ValueError:
                self.literals.add(item)

    def __contains__(self, host: str | None) -> bool:
        if self.always:
            return True
        if not host:
            return False
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return host in self.literals
        if ip in self.addresses:
            return True
        return any(ip in network for network in self.networks)
