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
- Next: Module 2 — CI/CD with GitHub Actions.
