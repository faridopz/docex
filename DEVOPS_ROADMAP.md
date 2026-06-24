# DOCex DevOps & Cloud Roadmap

> Goal: become job-ready as a DevOps / Cloud engineer by deploying DOCex
> properly on AWS, while earning AWS certifications.
> Approach: learn by doing on the real project. Every concept is taught
> with the *why*, not just the *how*.
>
> Owner: Farid · Cloud: AWS · Started: June 2026

---

## How to use this document

This is the spine of your training. Each module has:
- **Concepts** — what you must understand (and why it matters in a job)
- **Hands-on** — what we actually build/change in DOCex
- **Cert link** — which exam objective it maps to
- **Done when** — your checklist to move on

We do **one module at a time**. Don't rush ahead. Depth beats speed —
interviewers can tell the difference in 5 minutes.

---

## The mental model (read this first)

DevOps is the discipline of getting code from *your laptop* to *running
reliably in front of real users*, automatically and repeatably. Every tool
you'll learn exists to remove a manual, error-prone step from that journey.

The journey, end to end:

```
  CODE          PACKAGE        SHIP            RUN              WATCH
  ----          -------        ----            ---              -----
  write code →  build a    →   automate    →   run it on   →    monitor,
  + git         container       the build       cloud infra      alert,
                (Docker)        (CI/CD)         (AWS)            recover
                                                + define it
                                                as code
                                                (Terraform)
```

- **Code + Git** — version control, the source of truth. (You have this.)
- **Docker** — package the app so it runs identically everywhere. (Module 1)
- **CI/CD** — a robot that builds & tests every change. (Module 2)
- **AWS** — the computers in the cloud that actually run it. (Modules 3–4)
- **Terraform** — your infrastructure written as code, so it's repeatable
  and reviewable. (Module 5)
- **Observability** — knowing what's happening in production. (Module 6)

A DevOps engineer owns this whole pipe. That's the job.

---

## Why these specific tools (they're the industry standard)

| Tool | What it does | Why it, specifically |
|------|--------------|----------------------|
| Git | Version control | Universal. Non-negotiable. |
| Docker | Containerization | The default unit of deployment everywhere. |
| GitHub Actions | CI/CD | Free, built into where your code lives, huge market share. |
| AWS | Cloud platform | ~30% market share, the most job postings by far. |
| Terraform | Infra as Code | Cloud-agnostic, the most in-demand IaC tool. |
| CloudWatch | Monitoring | Native AWS observability; pairs with the cert. |

---

## Module 0 — Foundations & mental model  ⬅ START HERE

**Concepts**
- The deploy pipeline mental model (above)
- What "environments" are: local / staging / production, and why they exist
- Linux & the shell: filesystem, permissions, processes, env vars, pipes
- Git hygiene: what belongs in a repo, what never does (secrets!)
- The 12-Factor App principles (the philosophy behind modern deployment)

**Hands-on (on DOCex)**
- Audit the current setup: what runs where today (Railway + Vercel)
- Confirm secrets are out of git (✓ `.env` is gitignored)
- Tour the existing `api/Dockerfile`, `docker-compose.yml`

**Cert link** — AWS CP: "Cloud concepts" intro mindset.

**Done when** — you can explain, out loud, the path a code change takes from
your editor to a user's screen, and why each step exists.

---

## Module 1 — Containerization with Docker

**Concepts**
- The "works on my machine" problem and how containers solve it
- Image vs container (class vs instance)
- Dockerfile instructions, layers, and the build cache
- Why layer order matters (deps before code = faster rebuilds)
- Multi-stage builds (small, secure production images)
- `docker compose` for running multiple services together
- Volumes, ports, environment variables, networks

**Hands-on (on DOCex)**
- **Write the missing `web/Dockerfile`** (compose references it but it
  doesn't exist — `docker compose up` is currently broken)
- Build and run the full stack locally with one command
- Add a multi-stage build for the Next.js frontend
- Inspect images, read logs, exec into a running container

**Cert link** — foundational for ECS/Fargate later.

**Done when** — `docker compose up` brings up API + web, both reachable in
the browser, and you can explain every line of both Dockerfiles.

---

## Module 2 — CI/CD with GitHub Actions

**Concepts**
- Continuous Integration vs Continuous Delivery vs Deployment
- Why automate: catch bugs early, ship safely, remove human error
- Workflows, jobs, steps, runners, triggers
- Caching, matrix builds, secrets in CI
- Building & pushing images to a registry

**Hands-on (on DOCex)**
- A workflow that lints + type-checks + builds on every push/PR
- Build both Docker images in CI
- Push images to AWS ECR (ties into Module 3/4)
- Branch protection so nothing merges red

**Cert link** — AWS DevOps concepts; ECR.

**Done when** — every push runs checks automatically and a green build
produces published container images.

---

## Module 3 — AWS fundamentals + Cloud Practitioner cert

**Concepts**
- Account structure, the root user, and why you never use it day-to-day
- IAM: users, groups, roles, policies (least privilege)
- Regions & Availability Zones (and how to choose)
- The Shared Responsibility Model
- Core services: EC2, S3, VPC, RDS, ECS, ECR, CloudWatch, IAM
- Billing, the Free Tier, and budget alarms (so you never get surprised)

**Hands-on**
- Create + harden an AWS account (MFA on root, IAM admin user, budget alert)
- Install & configure the AWS CLI
- Poke each core service from the console and CLI

**Cert link** — **AWS Certified Cloud Practitioner (CLF-C02)**. First exam.

**Done when** — account is secured, you can navigate the console
confidently, and you're scoring well on CP practice exams.

---

## Module 4 — Deploy DOCex to AWS

**Concepts**
- Container registries (ECR)
- Compute options compared: EC2 vs ECS vs Fargate vs Lambda
- Networking: VPC, subnets (public/private), security groups, NAT
- Load balancers (ALB) and target groups
- Managed databases (RDS) vs your current Supabase
- TLS/HTTPS, domains (Route 53), certificates (ACM)
- Secrets in the cloud (Secrets Manager / SSM Parameter Store)

**Hands-on (on DOCex)**
- Push images to ECR
- Run the API + web on ECS Fargate
- Put them behind an ALB with HTTPS
- Wire secrets from Secrets Manager (no more plaintext env)
- Point a real domain at it

**Cert link** — AWS Solutions Architect Associate core.

**Done when** — DOCex is live on AWS at your own HTTPS domain, with secrets
managed properly.

---

## Module 5 — Infrastructure as Code (Terraform)

**Concepts**
- Why clicking in consoles doesn't scale (drift, no audit trail, not
  repeatable)
- Declarative vs imperative
- Terraform: providers, resources, state, `plan`/`apply`
- Variables, outputs, modules
- Remote state & locking (S3 + DynamoDB)

**Hands-on (on DOCex)**
- Re-create the entire Module 4 deployment in Terraform
- Tear it all down and stand it all back up from code
- Store state remotely

**Cert link** — heavily valued in DevOps roles; appears in interviews.

**Done when** — you can destroy and rebuild all of DOCex's infra with
`terraform apply`, and explain what state is.

---

## Module 6 — Observability, security & reliability

**Concepts**
- Logs vs metrics vs traces (the three pillars)
- CloudWatch dashboards & alarms
- Health checks, autoscaling, rolling deploys, rollbacks
- Backups & disaster recovery basics
- Security: least privilege, network isolation, secret rotation
- Cost monitoring as an ongoing practice

**Hands-on (on DOCex)**
- Centralize logs, build a dashboard
- Alarm on errors / high latency
- Autoscale the API under load
- Document a simple runbook

**Cert link** — SAA reliability & security pillars; Well-Architected.

**Done when** — you'd know within minutes if DOCex broke, and could explain
how you'd recover.

---

## Module 7 — Cert prep, portfolio & job readiness

**Concepts & actions**
- Sit **AWS Solutions Architect Associate (SAA-C03)** — the high-value cert
- Polish the DOCex repo as a portfolio centerpiece (README, architecture
  diagram, the Terraform, the CI/CD)
- Write a DevOps-focused resume around what you built
- Practice the common interview questions (Linux, networking, CI/CD,
  "walk me through a deployment", "how do you debug a down service")

**Done when** — cert passed, repo presentable, resume drafted, and you can
talk through your own architecture under questioning.

---

## Certification path (summary)

1. **AWS Certified Cloud Practitioner (CLF-C02)** — foundational, after Mod 3
2. **AWS Certified Solutions Architect – Associate (SAA-C03)** — the big one
   for employability, after Mod 6
3. *(Later, optional)* AWS Certified DevOps Engineer – Professional, or the
   Terraform Associate

---

## Progress log

Keep notes here as you go — what you learned, what confused you, what to
revisit. This becomes your study guide and interview prep.

- 2026-06-20 — Roadmap created. Starting Module 0.
- 2026-06-21 — Module 0 done (mental model, git hygiene audit, secrets).
- 2026-06-21 — Docker Desktop installed (Intel Mac). Ran first container
  (hello-world); learned image vs container, client/daemon, registry.
- 2026-06-21 — Module 1 milestone: wrote web/Dockerfile (multi-stage) +
  web/.dockerignore; fixed a real healthcheck bug in docker-compose.yml
  (curl not in image → switched to Python urllib). `docker compose up`
  now brings up the FULL stack (API + web) with health-gated startup.
  Decision: AWS will fully replace Vercel + Railway.
  TODO still in Module 1: shrink the 851MB web image via Next.js
  standalone output.
- 2026-06-21 — MODULE 1 COMPLETE. Enabled Next.js standalone output +
  rewrote runner stage → web image dropped from 851MB to a fraction.
  /verify confirmed working from the container. Learned atomic commits
  and cleared a stale git HEAD.lock along the way.
- 2026-06-21 — Module 2 underway: wrote .github/workflows/ci.yml. On every
  push to demo-release, GitHub builds BOTH images on clean runners.
  First run (CI #1) went GREEN in 1m52s. Also: re-pointed origin remote
  after repo rename, ignored *.log. CI (the "build & verify" half) is done.
  The CD half (auto-deploy) + pushing images to a registry both need an
  AWS home — so we pivot to Module 3 next.
- Next: Module 3 — AWS account setup + fundamentals (CP cert).
- 2026-06-22 — Module 3 hands-on DONE: AWS account on Free Plan; root MFA;
  zero-spend budget; IAM admin user (farid-admin) in Admins group w/
  AdministratorAccess + MFA; AWS CLI installed & configured (region
  eu-west-1). Verified with `aws sts get-caller-identity`.
  Real lessons hit & fixed: IAM deny-by-default (had to fix perms as root),
  rotated an exposed access key, and a clock-skew SignatureDoesNotMatch.
  Account ID: 656732270414. Still TODO in Mod 3: CP cert study.
- Next: Module 4 — push images to ECR, then run on ECS Fargate.
- 2026-06-23 — Module 4 progress: pushed both images to ECR; deployed the
  API to ECS Fargate behind an ALB (security groups: ALB open on :80,
  API only reachable from ALB on :8000), secret injected from Secrets
  Manager via a least-privilege execution role. API is LIVE:
  http://docex-alb-744821230.eu-west-1.elb.amazonaws.com/health -> 200.
  Used `aws logs tail` to read production CloudWatch logs (real debugging).
  KNOWN APP BUG (not infra): GET /openapi.json 500s due to a
  BaseHTTPMiddleware + GZipMiddleware interaction in api/main.py. /docs
  page loads but can't fetch its schema. Real endpoints work. Logged for
  later; deployment itself is proven correct.
- 2026-06-23 — Fixed the /openapi.json 500 properly. Root cause was NOT the
  middleware (a first guess off a truncated traceback) but a missing
  `Optional` import in api/knowledge_routes.py — invisible until schema-gen
  because `from __future__ import annotations` defers type resolution.
  Lesson: read the FULL traceback's bottom line before fixing; reverted the
  bad guess to keep the diff surgical. Shipped via rebuild->push->ECS
  force-new-deployment (zero-downtime rolling deploy). ALB /openapi.json now
  200. THE API IS FULLY LIVE AND HEALTHY ON AWS.
  Learned the core loop: change -> verify locally -> commit -> build -> push
  to ECR -> roll out -> verify in prod.
- 2026-06-23 — FRONTEND DEPLOYED. Added a NEXT_PUBLIC_API_URL build-arg to
  web/Dockerfile (NEXT_PUBLIC_* is baked at build time), rebuilt + pushed the
  web image with the API's ALB URL compiled in, deployed docex-web on Fargate
  behind its own ALB (deploy/create-web-service.sh). Fixed CORS by setting
  ALLOWED_ORIGINS on the API (task def rev 3) to the web ALB origin and
  redeploying — taught that config changes are versioned + rolled out like
  code.
  *** DOCex IS FULLY LIVE ON AWS, FRONT TO BACK ***
  Web:  http://docex-web-alb-926754058.eu-west-1.elb.amazonaws.com
  API:  http://docex-alb-744821230.eu-west-1.elb.amazonaws.com
- Module 4 core is DONE. Remaining polish: custom domain + HTTPS/TLS (ACM +
  Route 53), and cost-awareness/teardown. Then Module 5 redoes ALL of this
  as Terraform (IaC).
- NOTE: 2 ALBs + 2 Fargate tasks now running = burning Free-Plan credits.
  Fine for now; can tear down between sessions.
