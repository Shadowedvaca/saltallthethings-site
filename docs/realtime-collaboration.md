# Real-Time Collaboration Contract

SATT uses an authenticated Server-Sent Events (SSE) stream as a bounded hint
that canonical state has advanced. The signal is never an alternate data
source: a client that receives it reloads through the existing authenticated
canonical APIs and applies the existing revision/conflict contract.

## Transport decision

SSE over an authenticated streaming `fetch` fits the current FastAPI and
browser runtime, supports one-way server-to-client notification, and requires
no new broker, port, credential, or deployment service. WebSockets would add a
bidirectional protocol the product does not need. Fixed-interval client polling
would continue querying during idle periods and would make reconnect and
liveness behavior page-specific.

The server observes PostgreSQL's `satt.data_revision` from a new short-lived
session on every poll. A mutation's revision is therefore visible only after
the request transaction commits. A failed or rolled-back transaction is never
reported as a successful advance. This database-backed observation also works
across multiple application processes without an in-memory subscription
registry.

## Wire and authorization contract

`GET /api/sync/revisions?resource=canonical-state&after=<revision>` requires the
same Bearer token used by the existing authenticated APIs. The browser uses a
streaming `fetch` because native `EventSource` cannot attach that header.

The only eligible resource is currently `canonical-state`, matching the shared
state readable from `/api/export`. An event contains only a resource label and
monotonic revision:

```text
id: canonical-state:42
event: revision
data: {"resource":"canonical-state","revision":42}
```

It never includes changed domain names, records, Top 3 picks or reveal state,
proposals, usernames, credentials, database identifiers, or provider data.
Unknown resources return `404` without describing other subscriptions.

The server validates the signed token at connection establishment, verifies
that the account still exists and is active, and repeats account and token
lifetime checks while connected. An expired, deleted, or deactivated account
cannot establish a stream; an existing stream ends silently if authorization
ends. Environment isolation follows the same-origin API and environment-bound
database already enforced for development, test, and production.

## Lifetime, liveness, and cleanup

- The client supplies its last canonical revision with `after`; the server
  immediately sends a newer committed revision when one exists.
- The server checks for committed advances once per second and emits an SSE
  comment heartbeat after 15 idle seconds. Heartbeats contain no application
  metadata.
- Disconnect, cancellation, expiry, and account revocation terminate the async
  generator. The implementation creates no background task, handle, or
  in-memory subscription and closes every short-lived database session.
- Reconnect, backoff, duplicate suppression, canonical reload coordination, and
  dirty-edit behavior use the shared browser coordinator described below.

## Browser coordinator contract

Every authenticated management page loads `js/sync.js`. Authentication starts
one coordinator only after `Storage.init()` has loaded canonical state. Logout,
page navigation, and repeated initialization abort the prior fetch stream and
clear its retry timer.

The coordinator owns the latest observed and acknowledged revisions for
`canonical-state`. It ignores malformed, duplicate, delayed, out-of-order, and
wrong-resource events. When a signal is already reflected in Storage's current
revision, it is treated as a self-originated acknowledgement and does not cause
another reload or mutation. Otherwise one in-flight canonical `/api/export`
reload is shared by all signals; the stream never writes records.

After transport loss, the last acknowledged state remains visible. Adapters
receive `disconnected` with an actionable retry indication, and reconnect uses
a capped exponential delay from one to 30 seconds. Before opening the next
stream, a clean client reloads canonical state, so it converges even if signals
were missed. A `401` or missing local token ends retry rather than creating an
unauthorized loop.

Views register `onSyncStatus(status)` adapters instead of being mutated by the
transport. The status state is one of:

- `clean`: local view matches its acknowledged canonical revision;
- `dirty`: the view has an unsaved local edit;
- `refreshing`: canonical reload is in progress;
- `conflicted`: a newer revision arrived while a view was dirty;
- `disconnected`: transport or refresh failed and acknowledged state remains
  visible.

The shared coordinator never silently reloads a dirty view. Returning a view to
clean triggers one pending catch-up. Page-specific dirty detection, visible
messages, and keep/reload actions are added in #58; the coordinator contract is
already deterministic and transport-independent so those adapters do not own
connection or retry logic.

## Operations and rollback

No migration, external provider, secret, or infrastructure change is required.
The existing app container and reverse proxy carry the stream; buffering is
disabled for this response. Bounded application access logs can diagnose
authorization or response failures without logging token values or signal
payloads.

A code rollback removes the shared coordinator and subscription endpoint while
leaving canonical mutation and `If-Match` behavior unchanged. A missing or
disconnected notification stream leaves the last acknowledged state visible;
ordinary page reload and conflict recovery remain available. No database
rollback is needed.
