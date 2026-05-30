# End-to-End Test Plan

Project root: `/u01/app/agent_monitor`

## Goal

Provide one repeatable test plan and one visual board so any future session can see:
- overall architecture
- current runtime endpoints
- which test step is running now
- which step passed/failed
- what still blocks full production validation

## Runtime under test

### openclaw
- Agent service: `agent-monitor.service`
- Agent health: `http://127.0.0.1:2020/health`
- OEM webhook: `http://127.0.0.1:2020/webhook/oem`
- Google Chat command endpoint: `http://127.0.0.1:2020/google-chat/command`

### gcp
- Gateway service: `ggchat-app`
- Public fallback health: `http://118.69.205.10:2222/health`
- Public fallback alert receiver: `http://118.69.205.10:2222/agent/alerts`
- Public fallback Google Chat events endpoint: `http://118.69.205.10:2222/google-chat/events`

## Test tracks

### Track A — OEM -> Agent -> Gateway -> Google Chat

A1. Agent health check
A2. Gateway health check
A3. Signed synthetic OEM alert into Agent
A4. Agent rule match / incident save verification
A5. Agent outbound send verification to Gateway
A6. Gateway receive verification
A7. Google Chat webhook delivery verification if observable

### Track B — Google Chat -> Gateway -> Agent

B1. Gateway public health check
B2. Synthetic Google Chat message event into Gateway
B3. Gateway authorization check
B4. Gateway forward to Agent `/google-chat/command`
B5. Agent accept command and return `job_id`

## Success criteria

### Minimum success
- Track A through A6 passes
- Track B through B5 passes
- board status updates live and final state is saved

### Full success
- minimum success plus observable Google Chat delivery proof

## Current caveat

Google Chat final delivery may not be externally observable from local shell only. When unavailable, treat transport acceptance plus gateway success as sufficient internal proof and mark the final delivery step as `manual_verify`.

## Board requirements

The board must show:
- environment summary
- current endpoints
- flow diagram for both directions
- step list with statuses: `pending`, `running`, `passed`, `failed`, `manual_verify`
- last run timestamp
- notes / blockers

## Files to maintain
- board HTML: `docs/flow_test_board.html`
- board state JSON: `docs/flow_test_status.json`
- runner script: `scripts/run_flow_tests.py`
- plan: `docs/TEST_PLAN.md`

## Operator usage

1. Open board HTML in browser.
2. Run the runner script.
3. Refresh board if needed.
4. Read final statuses and blocker notes.
5. If DNS becomes healthy later, switch endpoints back to `https://gcp.leevo.top` and rerun.
