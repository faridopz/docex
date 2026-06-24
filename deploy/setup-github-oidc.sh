#!/usr/bin/env bash
#
# One-time setup so GitHub Actions can deploy to AWS WITHOUT stored keys.
# Creates: the GitHub OIDC provider, a deploy role scoped to this repo, and a
# least-privilege policy (push to ECR + roll out the two ECS services).
#
# Run once, from the project root:  bash deploy/setup-github-oidc.sh

set -euo pipefail
ACCOUNT=656732270414

echo "==> Ensuring GitHub OIDC provider exists..."
if aws iam list-open-id-connect-providers \
      --query 'OpenIDConnectProviderList[].Arn' --output text \
      | grep -q token.actions.githubusercontent.com; then
  echo "    already exists."
else
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bba01095a06bb1c87dba229b5bd5d9 \
                      1c58a3a8518e8759bf075b76b750d4f2df264fcd
  echo "    created."
fi

echo "==> Creating/Updating deploy role (docexGithubDeployRole)..."
if aws iam get-role --role-name docexGithubDeployRole >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name docexGithubDeployRole \
    --policy-document file://deploy/github-oidc-trust.json
  echo "    role existed — trust policy updated."
else
  aws iam create-role --role-name docexGithubDeployRole \
    --assume-role-policy-document file://deploy/github-oidc-trust.json >/dev/null
  echo "    role created."
fi

echo "==> Attaching least-privilege deploy permissions..."
aws iam put-role-policy --role-name docexGithubDeployRole \
  --policy-name docex-deploy \
  --policy-document file://deploy/github-deploy-policy.json

echo ""
echo "==> DONE. The workflow assumes this role:"
echo "    arn:aws:iam::${ACCOUNT}:role/docexGithubDeployRole"
