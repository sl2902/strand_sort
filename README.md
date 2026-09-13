# strand_sort

**AI-powered donation intake and sorting for food banks.**

Built for the AWS Strands Agents SDK Hackathon — *Good Neighbor* track.

---

## The Problem

Food banks receive far more donations than they can sort quickly.
Volunteers manually check expiry dates, decode nutrition labels, and
guess at dietary categories — one item at a time. It's slow,
error-prone, and pulls volunteer hours away from the work that actually
matters: getting food to the people who need it.

## Who It's For

Food bank staff and volunteers handling day-to-day donation intake —
anyone currently sorting shelves by hand, checking labels one item at a
time, and manually tracking what's expiring soon.

## Why It Matters

Food banks run on volunteer hours, not headcount. Every minute saved
sorting donations is a minute spent serving the community they exist
for.

---

## What It Does

Point a camera at a donation — a photo or a short video — and
`strand_sort`'s autonomous agent:

1. **Reads the label** — product name and category.
2. **Cross-checks the expiry date**, transcribing the exact printed text
   before parsing it, and reports its own confidence in the read.
3. **Reads dietary and nutrition symbols straight off the packaging** —
   the FSSAI vegetarian/non-vegetarian mark, nutrition panel values
   (sugar, sodium, protein), and derived flags like low-sugar/low-sodium
   — each tagged with whether it came from a printed symbol/panel, was
   inferred from general food knowledge, or is genuinely unavailable.
4. **Commits clean items straight to inventory**, or **flags anything
   uncertain for a quick human check** — a low-confidence date, physical
   damage, an unreadable label — rather than silently guessing.
5. **Tracks quantity and expiry status live** — items are deduplicated
   by product + expiry into a single batch record, and expiry status
   (fine / near-expiry / expired) is computed fresh on every read, not
   frozen at scan time.

A volunteer can then browse Inventory, resolve the Review queue, check
the Expiring tab, and distribute stock via a simple checkout action —
all without typing a single field by hand during intake.

---

## For Judges — Quick Start

There are two ways to see StrandSort in action, depending on how much
time you have:

### Fastest: the built-in narrated demo (`/demo`)

Visit **`https://strand-sort.vercel.app/demo`** and press play. This is a guided,
AI-narrated walkthrough (Gemini TTS) covering the problem, the pipeline,
and real example results — served entirely from static fixtures, with
**zero live backend calls**.

### Full experience: the live app

Visit **[StrandSort](https://strand-sort.vercel.app)** and try a real intake:

1. Go to the intake screen and either take a photo/short video of a
   single donated item, or upload one with different angles of the item.
2. Watch the agent extract the product name, expiry date, dietary marks,
   and nutrition values, each with its own confidence.
3. Confident, clean reads land directly in **Inventory**. Anything
   uncertain shows up in the **Review** queue, with the original photo
   next to the reason it was flagged.
4. Check the **Expiring** tab to see items nearing their expiry date,
   computed live rather than fixed at scan time.
5. Try **checkout** on an inventory item to see stock decrement, down to
   a disabled out-of-stock state at zero.

No AWS or GCP account is required to use either path — both are public,
hosted experiences.

---

## Architecture

```
┌─────────────┐      ┌──────────────────────────────┐      ┌────────────────┐
│  React/Vite  │ ───▶ │   AWS Lambda (container)      │ ───▶ │   Amazon S3     │
│  Frontend    │      │   FastAPI + Mangum             │      │  (donation      │
│              │ ◀─── │                                │      │   images)       │
└─────────────┘      │  ┌──────────────────────────┐  │      └────────────────┘
                      │  │ Strands Agent            │  │
                      │  │  - scan_package_batch    │  │      ┌────────────────┐
                      │  │  - commit_to_inventory   │  │ ───▶ │   DynamoDB      │
                      │  │  - rollback hook         │  │      │  (inventory,    │
                      │  │  - result-capture hook   │  │      │   review queue) │
                      │  └──────────────────────────┘  │      └────────────────┘
                      └───────────────┬────────────────┘
                                      │
                     ┌────────────────┴─────────────────┐
                     ▼                                   ▼
          ┌───────────────────┐              ┌───────────────────────┐
          │  Amazon Bedrock    │  fallback   │  Gemini (Vertex AI)     │
          │  (Amazon Nova)     │ ──────────▶ │  credentials via AWS    │
          │  primary vision    │             │  Secrets Manager on     │
          │  + agent reasoning │             │  Lambda, local ADC in   │
          └───────────────────┘             │  dev                     │
                                             └───────────────────────┘
```

**Direct-to-S3 uploads**: the browser uploads images/video frames
straight to S3 via presigned URLs, so intake requests to Lambda stay
small — bypassing the platform's payload limits regardless of photo
resolution.

**Automatic provider fallback**: if Bedrock is unavailable (model
access, quota, regional limits), both the vision extraction step and
the agent's own reasoning step fall back to Gemini on Vertex AI
automatically, mid-request — a single provider outage never stops
intake.

**Safety net**: a Strands hook captures the outcome of every tool call
in a request; if anything fails partway through, already-committed
inventory changes for that request are automatically rolled back rather
than left in a half-done state.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | [AWS Strands Agents SDK](https://strandsagents.com) |
| Vision & reasoning | Amazon Bedrock (Amazon Nova), Google Gemini via Vertex AI (fallback) |
| Compute | AWS Lambda (container image) |
| Storage | Amazon S3 (images), Amazon DynamoDB (inventory) — SQLite/local disk in dev |
| Secrets | AWS Secrets Manager (GCP service account credentials on Lambda) |
| Backend framework | FastAPI + Mangum |
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| Narration (demo) | Gemini TTS |
| Package management | `uv` (Python), npm/pnpm (frontend) |

---

## Key Features

- **Photo & video intake**, with multi-angle support for more accurate
  reads of a single item.
- **Confidence-aware extraction** — dates and nutrition values are
  never trusted blindly; every uncertain read routes to a human, and
  every dietary/nutrition flag is tagged with its actual source
  (printed symbol, printed panel, inferred, or unavailable).
- **Idempotent inventory** — a deterministic item ID (hashed from
  product name + expiry date) means re-scanning the same batch
  increments quantity instead of creating a duplicate row.
- **Human-in-the-loop review queue** for anything the agent isn't
  confident about, with the original photo shown alongside the flagged
  reason.
- **Dynamic expiry status**, computed live on every read — an item that
  was fine when scanned correctly shows as expired once its date
  passes, with no re-scan needed.
- **Distribution tracking** — a checkout action decrements stock, with
  a disabled/out-of-stock state once quantity reaches zero.
- **Click-to-enlarge photos** and generated thumbnails for fast-loading
  inventory browsing.
- **A guided, narrated in-app demo mode** (`/demo`) — a single button
  plays an AI-narrated walkthrough (Gemini TTS) covering the problem,
  the pipeline, and real (not staged) example results, entirely from
  static fixtures with zero live backend calls.

---

## Known Limitations

- **One item per scan, by design.** A single submission's photos/video
  are assumed to show one physical item from multiple angles, not
  multiple different products. Batching several different donations
  requires separate submissions.
- **Bedrock model access.** Full Claude-on-Bedrock access was pending
  approval at submission time; the system runs correctly end-to-end via
  its automatic Gemini fallback, and is architected to prefer Bedrock
  the moment access clears, requiring no code changes.

---

## Local Development

```bash
# Backend
uv sync
uv run uvicorn strand_sort.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` and fill in your own AWS/GCP credentials
and resource names (see `strand_sort/config.py` for the full settings
list). By default, the backend runs against local SQLite storage and
local disk for images (`storage_backend=local`, `db_engine=sqlite`) —
no AWS account required for local development.

---

## Deployment

The backend ships as a container image to AWS Lambda, exposed via a
Lambda Function URL. Set `storage_backend=s3` / `db_engine=dynamodb`
plus the relevant AWS/GCP environment variables for a real deployment.
See `Dockerfile` for the build definition.

### 1. Log in to AWS

If your organization uses AWS IAM Identity Center (SSO):

```bash
aws sso login --profile <your-profile-name>
```

If you're using long-lived access keys instead:

```bash
aws configure
```

Verify you're authenticated as the right identity before continuing:

```bash
aws sts get-caller-identity
```

### 2. Authenticate Docker to your ECR registry

```bash
aws ecr get-login-password --region <your-region> \
  | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<your-region>.amazonaws.com
```

### 3. Build and push the container image

```bash
docker build -t strand-sort .

docker tag strand-sort:latest \
  <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/strand-sort:latest

docker push <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/strand-sort:latest
```

### 4. Update the Lambda function to use the new image

```bash
aws lambda update-function-code \
  --function-name <your-function-name> \
  --image-uri <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/strand-sort:latest \
  --region <your-region>
```

### 5. (Optional) Invoke the function directly to test

```bash
aws lambda invoke \
  --function-name <your-function-name> \
  --region <your-region> \
  --payload '{}' \
  response.json

cat response.json
```

### 6. (Optional) Tail logs for a live invocation

```bash
aws logs tail /aws/lambda/<your-function-name> --follow --region <your-region>
```

Replace every `<your-...>` placeholder above with your actual AWS
account ID, region, function name, and ECR repository name.

---

## License

This repository is public and licensed under the [MIT License](./LICENSE).
An open-source license file must be present at the repository root for
hackathon submission requirements — GitHub's automatic license detection
reads it from there and surfaces it in the repo's "About" section.