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

![strand_sort_architecture](/assets/strandsort_architecture_v2.png)

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

## AWS Setup — Provisioning Resources From Scratch
 
The commands below create every AWS resource this project needs. If
you're deploying against an existing setup, skip to **AWS Deployment**
further down instead.
 
**Region note**: the commands below use `ap-south-1` to match how the
DynamoDB table and S3 bucket were actually created for this project —
adjust if you're provisioning elsewhere, but keep it consistent across
every command and every Lambda environment variable.
 
### 1. Create the DynamoDB table
 
```bash
aws dynamodb create-table \
  --table-name strand-sort-inventory \
  --attribute-definitions \
    AttributeName=item_id,AttributeType=S \
    AttributeName=product_name,AttributeType=S \
    AttributeName=idempotency_key,AttributeType=S \
  --key-schema AttributeName=item_id,KeyType=HASH \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "ProductNameIndex",
        "KeySchema": [{"AttributeName": "product_name", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
      },
      {
        "IndexName": "IdempotencyKeyIndex",
        "KeySchema": [{"AttributeName": "idempotency_key", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]' \
  --billing-mode PAY_PER_REQUEST \
  --region ap-south-1
```
 
### 2. Create the S3 bucket and set CORS for direct browser uploads
 
```bash
aws s3api create-bucket \
  --bucket strand-sort-images \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1
 
aws s3api put-bucket-cors \
  --bucket strand-sort-images \
  --cors-configuration '{
    "CORSRules": [
      {
        "AllowedOrigins": ["http://localhost:5173", "https://strand-sort.vercel.app"],
        "AllowedMethods": ["PUT"],
        "AllowedHeaders": ["*"],
        "MaxAgeSeconds": 3000
      }
    ]
  }'
```
 
Update `AllowedOrigins` if your local dev port or deployed frontend URL
differs.
 
### 3. Store the GCP service account credentials in Secrets Manager
 
Needed because Lambda has no local ADC (Application Default Credentials)
file — this is what `gcp_auth.py`'s `get_gcp_credentials()` reads on cold
start.
 
```bash
aws secretsmanager create-secret \
  --name strand-sort/gcp-service-account \
  --secret-string file://path/to/your-gcp-service-account.json \
  --region ap-south-1
```
 
The secret name here matches `gcp_secrets_manager_secret_id`'s default in
`config.py` — if you use a different name, set that env var to match.
 
### 4. Create the IAM role and permissions policy for Lambda
 
```bash
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
 
aws iam create-role \
  --role-name strand-sort-lambda-role \
  --assume-role-policy-document file://trust-policy.json
 
cat > permissions-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-south-1:<your-account-id>:table/strand-sort-inventory",
        "arn:aws:dynamodb:ap-south-1:<your-account-id>:table/strand-sort-inventory/index/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::strand-sort-images/*"
    },
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-south-1:<your-account-id>:secret:strand-sort/gcp-service-account-*"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-south-1:<your-account-id>:*"
    }
  ]
}
EOF
 
aws iam put-role-policy \
  --role-name strand-sort-lambda-role \
  --policy-name strand-sort-lambda-permissions \
  --policy-document file://permissions-policy.json
```
 
Replace `<your-account-id>` with your actual AWS account ID
(`aws sts get-caller-identity` shows it).
 
### 5. Create the ECR repository
 
```bash
aws ecr create-repository \
  --repository-name strand-sort \
  --region ap-south-1
```
 
### 6. Build, push, and create the Lambda function
 
Follow **steps 1–3 of AWS Deployment** below to authenticate Docker and
push your first image, then create the function (rather than update an
existing one):
 
```bash
aws lambda create-function \
  --function-name strand-sort \
  --package-type Image \
  --code ImageUri=<your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/strand-sort:latest \
  --role arn:aws:iam::<your-account-id>:role/strand-sort-lambda-role \
  --timeout 60 \
  --memory-size 1024 \
  --region ap-south-1 \
  --environment "Variables={
    AWS_REGION=ap-south-1,
    DB_ENGINE=dynamodb,
    DYNAMODB_TABLE_NAME=strand-sort-inventory,
    STORAGE_BACKEND=s3,
    S3_BUCKET_NAME=strand-sort-images,
    GCP_PROJECT_ID=<your-gcp-project-id>,
    GEMINI_LOCATION=<your-gemini-location>,
    GCP_SECRETS_MANAGER_SECRET_ID=strand-sort/gcp-service-account
  }"
```
 
`GCP_PROJECT_ID` and `GEMINI_LOCATION` are required with no code default
— the function will fail at cold start without them.
 
### 7. Expose it via a Lambda Function URL
 
```bash
aws lambda create-function-url-config \
  --function-name strand-sort \
  --auth-type NONE \
  --region ap-south-1
 
aws lambda add-permission \
  --function-name strand-sort \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --region ap-south-1
```
 
`--auth-type NONE` makes this publicly invokable, matching a public demo
app with no login required — tighten this if that's not appropriate for
your deployment.
 
---
 
## AWS Deployment
 
Use this section once the resources above already exist, to ship a code
update to the running Lambda function.
 
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