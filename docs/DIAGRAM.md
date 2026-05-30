# Agent GCP Diagrams

## High-level architecture

```mermaid
flowchart LR
    OEM[OEM umarket\n10.10.10.112] -->|OS Command signed webhook| AGENT[Agent Monitor openclaw\n10.10.10.110:2020\n/u01/app/agent_monitor]
    AGENT -->|Processed alert + HMAC\nhttps://gcp.leevo.top/agent/alerts| GCP[GCP Gateway gcp\n10.10.10.113:2222\n/u01/app/ggchat_app]
    GCP -->|cardsV2/webhook| CHAT[Google Chat Space]
    CHAT -->|slash/message event| GCP
    GCP -->|POST /google-chat/command\nX-Gateway-Secret| AGENT
    AGENT -.future callback.->|POST /agent/callback| GCP
```

## Alert sequence

```mermaid
sequenceDiagram
    participant OEM as OEM umarket
    participant A as Agent openclaw:2020
    participant DB as PostgreSQL monitor DB
    participant G as GCP gateway gcp:2222
    participant C as Google Chat

    OEM->>A: POST /webhook/oem + X-Signature
    A->>A: verify AGENT_WEBHOOK_SECRET
    A->>A: mask, match rule, RCA
    A->>DB: insert incident/audit
    alt matched rule
        A->>G: POST https://gcp.leevo.top/agent/alerts + HMAC
        G->>G: verify AGENT_SHARED_SECRET
        G->>C: send Google Chat card
        G-->>A: 202 accepted
    else no matched rule
        A-->>OEM: 202 accepted, gcp_sent=false
    end
```

## Command sequence

```mermaid
sequenceDiagram
    participant C as Google Chat
    participant G as GCP gateway
    participant A as Agent openclaw:2020
    participant OEM as OEM/DB tools

    C->>G: POST /google-chat/events
    G->>G: validate user/domain
    G->>A: POST /google-chat/command + X-Gateway-Secret
    A->>A: validate shared secret
    A-->>G: 202 accepted + job_id
    Note over A,OEM: Future: execute allowlisted DBA/OEM command
    A-.->>G: POST /agent/callback + HMAC
    G-.->>C: threaded reply
```

## Runtime ports

| Host | Service | Port | Scope |
|---|---|---:|---|
| openclaw | `agent-monitor.service` | `2020` | Agent brain + dashboard |
| openclaw | old `monitor-v2-agent.service` | `8080` | disabled/inactive |
| gcp | `ggchat-app.service` | `2222` | local loopback Google Chat gateway |
| gcp | `cloudflared.service` | n/a | exposes `gcp.leevo.top` to app port 2222 |
```
