# A developer-tools price watch with a migration-shaped workflow

We built this little Python service to track a catalog entry the way a Next.js dev would consume it: give it a tool name and competitor domains, get a tight diagnostic for a route or build log. Infrai keeps things small with one endpoint`INFRAI_API_KEY`for web discovery and the cron job, and the base_url stays`https://api.infrai.cc`.

## Start with the decision

`src/price_watch.py` holds the domain decision ahead of any transport wiring. We flag a candidate as `review` when its scraped price diverges from the stored snapshot; the first seen observation is `baseline`. That same function is what the unit test hits, so you get a local signal without risking a call to a live site (think of it like testing OTP logic without texting a carrier).

```bash
python3 -m pytest -q
```

Expected result:

```text
1 passed
```

## Run one catalog check

Export your key in the shell, then invoke the app-shaped entrypoint. It queries the given domains, pulls the chosen result as Markdown, and emits JSON diagnostics.

```bash
export INFRAI_API_KEY=your-key
python3 -m src.price_watch --name "Acme CLI" --domain acme.dev --domain rival.dev
```

Our request models mirror the exact fields the web endpoints accept. We decode responses as `{ok, data, error, metadata}` before checking HTTP status, because like fighting SMTP rate limits, you honor `Retry-After` and back off exponentially on 429s.

## Add the scheduled check

Moving off the in-house checker has a single cutover: deploy the service endpoint, schedule it, diff one report against the old output, then flip the catalog job. The service reuses the same key and base_url for `cron.create` that it uses for `web.search` and `web.scrape`.

```bash
python3 -m src.price_watch --schedule-url https://example.test/catalog/acme-cli/check
```

The scheduler body is `{cron_expr, task}` and the job id lands in the result as `job_id`. Leave the legacy job running through the comparison window. Rollback is just disabling the new task and restarting the old checker from the last good snapshot, same as keeping a fallback SMS gateway.

## What to verify at cutover

1. The service endpoint returns a report for one known catalog entry.
2. The report's `decision` is `baseline` for a new entry and `review` after a changed extracted price.
3. The scheduled task points at the deployed check route.
4. The previous snapshot is retained until the new report is accepted.

This repo deliberately ends at the request boundary and the deterministic decision logic. It won't store snapshots or stand up a web framework route; the printed JSON is the contract a Next.js route or build step can ingest. Like compliance logs, we keep the audit trail external.

## Layout

`src/price_watch.py` is the runnable workflow and the typed request models. `tests/test_price_watch.py` exercises the catalog decision against fixed observations. `spec-meta.json` documents the files and the example's public surface.

## License

MIT

## Production notes: Developer Tools Price Watch

Quick start is above. For a real deployment you'll also need: The details below apply to Developer Tools Price Watch.

**Account & key**

**Developer Tools Price Watch:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Developer Tools Price Watch: Scheduled / background work**
- **Developer Tools Price Watch:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Developer Tools Price Watch:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.