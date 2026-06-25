# DOCex — Engineering Case Study

How a real document-AI product was taken from "runs on my laptop" to a
production-grade AWS deployment: containerized, continuously deployed, and
fully defined as Infrastructure as Code.

---

## Context

DOCex is an AI document-intelligence tool born from a real problem — NGO
sub-award teams in Abuja drowning in hundreds of application documents per
cycle. The application logic (FastAPI + Anthropic Claude + a retrieval layer)
already worked. The goal of this effort was to make it **deployable, reliable,
and reproducible** — to run it like a product people pay for, not a demo.

This document focuses on the platform/DevOps work and the decisions behind it.

---

## Goals

1. Package the app so it runs identically everywhere (kill "works on my machine").
2. Ship changes automatically and safely, with no manual steps.
3. Run it on real cloud infrastructure I control and understand.
4. Make the whole environment reproducible and reviewable as code.
5. Do all of the above with production-grade security defaults.

---

## Key decisions (and why)

**ECS Fargate over EC2 or a PaaS.** Fargate runs containers without managing
servers — the right level of abstraction to *learn* real cloud primitives (VPC,
ALB, target groups, IAM) without also babysitting OS patching. A PaaS (the app's
original Railway/Vercel home) hid exactly the layers worth understanding.

**OIDC over stored CI credentials.** The pipeline authenticates to AWS by having
GitHub assume a least-privilege IAM role via OIDC, getting a short-lived token
per run. No long-lived AWS keys live in GitHub secrets — eliminating the most
common cloud-credential leak vector.

**Secrets Manager over environment variables.** The Anthropic API key is stored
encrypted and injected into the container at launch via the task definition's
`secrets` block. It never appears in code, the image, the task definition, or
logs. The execution role can read *only* that one secret.

**Terraform over click-ops.** Console clicking doesn't scale, drifts, and leaves
no audit trail. Terraform makes the infrastructure a reviewable artifact that can
be reproduced or destroyed and rebuilt on command.

---

## The build, in five stages

1. **Containerize.** Multi-stage Dockerfiles for both services; Next.js
   "standalone" output cut the web image ~80%. `docker compose` runs the full
   stack locally with a health-gated startup order.
2. **CI.** GitHub Actions builds both images on every change — proving the app
   builds on a clean machine, not just locally.
3. **Cloud.** Pushed images to ECR; ran both services on ECS Fargate behind
   Application Load Balancers; wired secrets via Secrets Manager; centralized
   logs in CloudWatch — all inside a VPC with least-privilege security groups
   (ALBs open on :80; tasks reachable *only* from their ALB).
4. **CD.** Extended the pipeline so a push auto-builds, pushes to ECR, and rolls
   out a zero-downtime deployment — authenticated by OIDC.
5. **IaC.** Imported the entire running stack into Terraform with zero downtime.

---

## Problems solved (the interesting part)

**A production 500, diagnosed from logs.** After deploy, `/openapi.json` returned
500 while `/health` was fine. Rather than guess, I pulled the live container's
CloudWatch logs (`aws logs tail`) and read the traceback to its root: a Pydantic
model that referenced `Optional` without importing it — invisible until
schema-generation time because `from __future__ import annotations` defers type
resolution. One-line fix, verified locally, shipped through the deploy pipeline.
*Lesson: read the full traceback's bottom line before fixing; an early guess
(blaming middleware) was wrong and was reverted to keep the change surgical.*

**A health check that could never pass.** The compose health check ran `curl`
inside an image that didn't include `curl`. Switched it to the Python HTTP client
that *was* in the image. *Lesson: a health check can only use tools that exist in
the container.*

**Brownfield Terraform import with zero downtime.** The infrastructure already
existed from manual setup, so I adopted it into Terraform using `import` blocks
rather than recreating it (which would have meant downtime and new URLs for a
live product). This surfaced the real craft of import: reconciling
provider-vs-AWS default mismatches (e.g. target-group health thresholds, AZ
rebalancing) until `terraform plan` reported **"No changes"** — config faithfully
matching reality. Task definitions were *defined* in Terraform (immutable,
versioned artifacts) and services rolled onto them with zero downtime.

**Operational gotchas, handled.** Clock skew causing `SignatureDoesNotMatch`;
ECS service-linked-role bootstrapping on a fresh account; a stale CloudFormation
stack from a failed console action; a region mismatch (resources in `eu-west-1`,
console on `eu-north-1`). Each is a small but real lesson in how cloud systems
actually behave.

---

## Outcome

- A live, two-service application on AWS Fargate, load-balanced and
  secret-managed.
- Push-to-deploy CI/CD with no stored credentials and zero-downtime rollouts.
- The entire stack reproducible from Terraform; tear down to save cost, rebuild
  in minutes.
- A clean operating model: **app changes ship via the pipeline; infrastructure
  changes go through Terraform** — never the console.

---

## What's next

- **HTTPS + custom domain** (ACM cert, Route 53) — customer-facing polish.
- **Durable data + multi-tenancy** — move from ephemeral container storage to a
  managed database (and per-user data isolation) so the product can serve many
  customers.
- **Observability** — CloudWatch dashboards and alarms for fast incident
  detection.
- **Remote Terraform state** (S3 + DynamoDB lock) for safe, shared state.

---

*Stack: Next.js · FastAPI · Anthropic Claude · BM25 retrieval · Docker · AWS
(ECS Fargate, ECR, ALB, VPC, Secrets Manager, CloudWatch, IAM) · GitHub Actions
(OIDC) · Terraform.*
