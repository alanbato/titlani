# Run Behind a TCP Relay (PROXY Protocol)

This guide shows you how to run Titlani behind a TCP relay, such as Traefik, HAProxy, or nginx `stream`, and still see each client's real IP address.

## When You Need This

You might put a relay in front of Titlani when the server has no public IP of its own. For example, a home server behind CG-NAT can be reached through a small public VPS that forwards ports 1958 and 1960 over a VPN or Tailscale.

The relay must do **raw TCP passthrough**. Misfin and GMAP use client certificates, so TLS has to end at Titlani, not at the relay.

Without extra setup, every connection appears to come from the relay. As a result:

- [Rate limiting](rate-limiting.md) puts all clients in one shared bucket
- [Access control](access-control.md) lists only ever see the relay's IP
- Logs lose the real client addresses

The PROXY protocol fixes this. The relay sends a small header with the client's address before the TLS handshake. Titlani reads the header and uses that address for rate limiting, access control, and logs.

## Configure Titlani

Add a `[proxy_protocol]` section to your server config:

```toml
[proxy_protocol]
enable = true
# Addresses of your relay(s), as seen by Titlani. IPs or CIDRs, IPv4 or IPv6.
trusted_sources = ["100.64.0.1", "fd7a:115c:a1e0::1"]
# Seconds a relay has to send the header before the connection is dropped.
header_timeout = 5.0
```

This applies to both the Misfin listener and the GMAP listener.

!!! warning "Keep `trusted_sources` tight"
    A PROXY header can claim any client address. Only list the relay's own addresses. Any host in `trusted_sources` can make its connections look like they come from somewhere else.

## Configure the Relay

The relay must send **PROXY protocol version 2** (version 1 also works) to Titlani on both ports.

=== "Traefik"

    ```yaml
    tcp:
      routers:
        misfin:
          entryPoints: ["misfin"]
          rule: "HostSNI(`*`)"
          service: misfin
        gmap:
          entryPoints: ["gmap"]
          rule: "HostSNI(`*`)"
          service: gmap
      services:
        misfin:
          loadBalancer:
            proxyProtocol:
              version: 2
            servers:
              - address: "100.101.102.103:1958"
        gmap:
          loadBalancer:
            proxyProtocol:
              version: 2
            servers:
              - address: "100.101.102.103:1960"
    ```

    Don't add a `tls` block to these routers. Titlani must terminate TLS itself. Newer Traefik releases also allow setting `proxyProtocol` on a TCP `serversTransport`. Check the docs for your version.

=== "HAProxy"

    ```text
    frontend misfin
        mode tcp
        bind :1958
        default_backend misfin

    backend misfin
        mode tcp
        server home 100.101.102.103:1958 send-proxy-v2
    ```

    Repeat for GMAP on port 1960.

=== "nginx"

    ```nginx
    stream {
        server {
            listen 1958;
            proxy_pass 100.101.102.103:1958;
            proxy_protocol on;
        }
        server {
            listen 1960;
            proxy_pass 100.101.102.103:1960;
            proxy_protocol on;
        }
    }
    ```

## How Connections Are Handled

| Connection from | PROXY header | Result |
|-----------------|--------------|--------|
| A trusted relay | Valid | Client IP taken from the header |
| A trusted relay | `LOCAL` (health check) | Relay's own IP is used |
| A trusted relay | Missing, malformed, or too slow | Connection dropped and logged |
| Any other host | Present | Connection dropped and logged (never trusted) |
| Any other host | Absent (plain TLS) | Direct connection with its real IP |

Other hosts can still connect directly, for example from inside your private network. If the relay should be the only way in, block direct access with a firewall.

## Verify It Works

Start the server. The startup summary shows the setting:

```text
PROXY Protocol   Enabled (trusted: 100.64.0.1)
```

Then send a message through the relay. With `--log-level DEBUG`, the `connection_established` events show the sender's real IP (hashed in the logs for privacy) instead of the relay's IP.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `proxy_protocol_invalid_header` with `missing PROXY protocol header` | The relay isn't sending PROXY protocol, or a non-relay host is listed in `trusted_sources`. |
| `proxy_protocol_untrusted_source` | The relay's address isn't in `trusted_sources`. Use the address Titlani sees (for Tailscale, the relay's tailnet IP). |
| `proxy_protocol_timeout` | The relay connected but didn't send a header within `header_timeout`. |
| `tls_error` for every connection | The relay sends PROXY protocol but `[proxy_protocol]` isn't enabled on Titlani. |
| Config error: `requires at least one entry in proxy_protocol.trusted_sources` | `enable = true` was set without any trusted sources. |

## See Also

- [Configuration reference](../reference/configuration.md#proxy_protocol)
- [Rate Limiting](rate-limiting.md)
- [Deploy to Production](deploy-to-production.md)
