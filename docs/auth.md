# Authentication, Roles, and CR Access

Google-only sign-in, restricted to the institute email domain (with one
explicit test exception), server-verified roles, and a request/approval
workflow for Class Representative access. Full auth flow: browser → Supabase
Auth (Google) → database-enforced domain gate → session cookies → role/
profile-aware routing.

## 1. Sign-in

**Google only** — no email/password, no student-ID form (both existed as UI
mockups before this and are removed). `src/routes/login.tsx` calls:

```ts
supabase.auth.signInWithOAuth({
  provider: "google",
  options: { redirectTo: `${window.location.origin}/auth/callback` },
});
```

Google OAuth was already enabled on the Supabase project (client ID/secret
configured in Auth → Providers → Google) before this work — verified via the
Management API (`external_google_enabled: true`) rather than assumed.

### Domain restriction (database-enforced, not client-side)

Every sign-in — Google or otherwise — passes through a Postgres **Before
User Created** Auth Hook before an account is created:

```sql
-- supabase/migrations/20260913000001_auth_signup_and_role_security.sql
create function public.hook_restrict_signup_by_email_domain(event jsonb)
returns jsonb ...
```

Rule: accept `%@iiitkottayam.ac.in`, accept the single test exception
`oduri.johnson@gmail.com`, reject everything else with a clear message
returned straight to the client (`403`, no generic "signup failed"). This
cannot be bypassed from the browser — it runs inside the database.

**Verified** (live, via the real public signup endpoint, not the
service-role admin API which intentionally bypasses this hook the same way
it bypasses RLS):

| Email | Result |
|---|---|
| `blocked-random@gmail.com` | `403` — rejected with the institute-email message |
| `odurijohnson24bcs66@iiitkottayam.ac.in` | `200` — accepted |
| `oduri.johnson@gmail.com` | `200` — accepted (test exception) |

### Role assignment on signup

`handle_new_user()` (the existing `auth.users` insert trigger, extended)
sets the initial role directly — never left to a default a client could
race:

- `oduri.johnson@gmail.com` → `ADMIN` (verified live).
- Every other accepted signup → `STUDENT` (verified live).

`ADMIN` is the one role allowed into every portal (see §3) — this single
role satisfies "access to both admin and CR portals" for the test account,
rather than adding multi-role support to the schema.

## 2. Sessions (cookies, not localStorage/bearer headers)

- **Browser**: `src/lib/supabase-browser.ts` — `@supabase/ssr`'s
  `createBrowserClient`, session stored in cookies.
- **Server** (server functions, API routes): `src/lib/supabase-server.ts` —
  `getSupabaseSessionClient(request, onSetCookies?)`, reads the session from
  the request's `Cookie` header via `@supabase/ssr`'s `createServerClient`.
  Still anon-key only, still RLS-scoped to the resolved `auth.uid()` — never
  service-role for a user request (unchanged rule, CLAUDE.md §13).
- **OAuth callback** (`src/routes/auth/callback.tsx`): the one place that
  writes cookies — exchanges `?code` for a session
  (`exchangeCodeForSession`), then decides the destination server-side in
  the same request (role → `/complete-profile` if the academic profile is
  incomplete, else the role's portal) and redirects in one hop.

This replaces the timetable API's original bearer-header forwarding for
*user-facing browser sessions* — `getSupabaseForRequest` (bearer header)
still exists for any non-browser caller that supplies its own token
directly (e.g. `scripts/verify_query_router.py`'s test-student sign-in).
Both paths land on the same security model: anon key, RLS, `auth.uid()`
resolved server-side, never trusted from the client.

## 3. Roles and route guards

Four roles (`profiles.role`): `STUDENT`, `FACULTY` (unused so far),
`CR`, `ADMIN`.

`src/components/auth/auth-gate.tsx` wraps every page that uses `AppShell`
(dashboard, timetable, courses, faculty, mess, cr, admin, …):

```tsx
<AppShell allow={["ADMIN"]}>       {/* /admin */}
<AppShell allow={["CR"]}>          {/* /cr */}
<AppShell>                          {/* everything else — any signed-in role */}
```

Behavior:

1. Not authenticated → `/login`.
2. `STUDENT`/`CR` with an incomplete academic profile → `/complete-profile`
   (skipped for `ADMIN`, which has no student profile to complete).
3. Role not in `allow` → sent to their own portal
   (`ADMIN → /admin, CR → /cr, STUDENT → /dashboard`) — **except `ADMIN`,
   which always passes**, matching "admin should reach both admin and CR
   portals."

**This is a UX convenience, not the security boundary** — every data
operation behind these pages is independently protected by RLS +
`is_admin()`/`orion_resolve_user()` regardless of whether this redirect
fires first (AGENTS.md §7: never trust client-side role checks for
authorization). The real boundary is enforced whether or not the guard ever
runs — verified directly against the database with raw HTTP calls, not just
through the UI (§5).

**Known limitation**: the guard runs client-side (`useEffect` after
mount/hydration), so a hard-refreshed protected page can flash briefly
before redirecting. An SSR-level guard (checking the session in each
route's `beforeLoad`) would close this gap; not implemented in this pass.
The data itself was never exposed during that flash — RLS still applied to
every query the flashed page made.

## 4. Onboarding (`/complete-profile`)

Collects exactly what ORION's chat/timetable context needs
(`orion_student_context` reads `student_profiles` — docs/query-router.md):
full name, admission year, programme/branch, semester, batch.

`batch` and `section` are collected as one field and written to both
columns — the ingested timetable data always sets them equal
(`backend/timetable/normalizer.py`: `section=meta.batch`), so asking the
student for a distinction the source data doesn't have would only invite a
wrong answer.

`src/lib/onboarding-api.ts`'s `completeOnboarding` writes:
- `student_profiles` (upsert, self-row only — RLS added in this migration,
  previously `student_profiles` had no INSERT/UPDATE policy at all, only
  SELECT-own)
- `profiles.full_name` / `profiles.admission_year` (self-update — pre-existing
  policy, unchanged)

**Verified live**: a fresh test account with no `student_profiles` row was
redirected to `/complete-profile` on first authenticated visit to
`/dashboard`; submitting the form wrote the correct row
(`department=ELECTRONICS AND COMMUNICATION ENGINEERING, batch=II,
section=II, semester=1, admission_year=2026`) and the same account was no
longer redirected there afterward.

## 5. CR access: request → admin approval → role flip

Never self-service. A `STUDENT` requests; only an `ADMIN` can grant it.

```
STUDENT clicks "Request CR access" (account menu)
  → requestCrAccess() inserts approval_requests
      (submission_type='cr_access_request', submitted_by=auth.uid())
  → ADMIN sees it in /admin's "CR access requests" queue
  → approves/rejects → review_cr_access_request(request_id, approve, reason?)
      - admin-only (checked inside the function, not just RLS)
      - flips profiles.role → 'CR' on approval
      - writes audit_logs (actor, action, entity, old/new)
```

### Why a role can't be self-escalated

`profiles_update_own` (pre-existing RLS policy) lets a user update their
own profile row with **no column restriction** — meaning, unguarded, any
authenticated user could `PATCH` their own `role` straight to `'ADMIN'`.
This was a real gap, found while designing the CR workflow, not a
hypothetical: fixed with a `BEFORE UPDATE` trigger
(`prevent_role_self_escalation`) that rejects any row where `role` changed
and the actor isn't already an admin. Role changes only ever happen through
`review_cr_access_request` or a direct admin `UPDATE` (allowed by the new
`profiles_update_admin_all` policy) — never through a student's own request.

**Verified live**, all via real HTTP calls against the hosted project
(not simulated):

| Step | Result |
|---|---|
| Student attempts `PATCH profiles?id=eq.<self>` with `{"role":"ADMIN"}` | `400` — `"Only an administrator can change a user's role."` |
| Student inserts `approval_requests` (`cr_access_request`, own id) | `201` |
| Student `SELECT`s `approval_requests` | sees only their own row (RLS) |
| Admin calls `review_cr_access_request(id, true)` | `204` |
| Student's `profiles.role` afterward | `CR` |
| `audit_logs` | one row: `cr_access_approved`, actor = admin, entity = the request |

## 6. Live verification summary (2026-09-13)

Two layers, both against the real hosted Supabase project and a real
running dev server — not mocked:

**Direct HTTP/RLS** (`requests` against `/auth/v1/*` and `/rest/v1/*`):
domain restriction, role assignment, self-escalation block, student
self-onboarding RLS, CR request submission + isolation, admin-only
approval RPC, audit logging — see §1/§4/§5 tables above.

**Real browser** (Playwright, headless Chromium, `npm run dev`):
1. `/login` renders; clicking "Continue with Google" redirects to
   `accounts.google.com` with the correct `client_id` and
   `redirect_to=http://localhost:8080/auth/callback`.
2. A `CR`-role session visiting `/dashboard` shows the real role badge;
   visiting `/admin` is redirected to `/cr` (their own portal).
3. An `ADMIN` session on `/admin` sees the CR access requests queue with
   the real requester listed; visiting `/cr` is allowed (admin bypass).
4. A fresh account with no academic profile is redirected to
   `/complete-profile` on its first protected-page visit; submitting the
   form redirects to `/dashboard` and is never sent back.

Full click-through of the actual Google consent screen was not tested (no
real Google account credentials in this environment) — everything up to
and after that point (redirect construction, the domain hook, the callback
exchange logic, session cookies, route guards, onboarding, CR approval) was
verified directly.

## 7. Known gaps / next steps

- **SSR-level route guards** — currently client-side only (§3); the actual
  data is still protected regardless, but a hard refresh can flash content
  briefly before redirecting.
- **`FACULTY` role** is defined in the schema/CHECK constraint but has no
  signup path, portal, or route guard behavior yet.
- **Production redirect URL** — `site_url`/`uri_allow_list` are currently
  set to `http://localhost:8080` only; add the deployed origin before
  shipping past local development (Supabase dashboard → Auth → URL
  Configuration, or the same Management API call used to set the dev
  value).
- **Test accounts left live** on the project from verification:
  `odurijohnson24bcs66@iiitkottayam.ac.in` (now role `CR`, from the
  approval-flow test), `oduri.johnson@gmail.com` (role `ADMIN`, the
  intended test account), `freshstudent25bcs01@iiitkottayam.ac.in` (role
  `STUDENT`, complete profile, from the onboarding test). None are
  destructive to remove if a clean slate is wanted — just re-run the
  relevant flow again afterward to re-verify.
