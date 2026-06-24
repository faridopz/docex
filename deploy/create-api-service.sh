#!/usr/bin/env bash
#
# Creates the public-facing infrastructure for the DOCex API on ECS Fargate:
#   - finds your account's default VPC + subnets
#   - 2 security groups (firewall rules)
#   - an Application Load Balancer (public front door)
#   - a target group (where the ALB sends traffic) with a /health check
#   - a listener (ALB port 80 -> target group)
#   - the ECS service (keeps 1 task running, wired to the load balancer)
#
# Run once, from the project root:  bash deploy/create-api-service.sh
# Resource IDs are saved to deploy/api-service-ids.txt for later use.

set -euo pipefail          # stop on any error; fail loudly
REGION=eu-west-1

echo "==> Looking up default VPC and subnets..."
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --region $REGION --query 'Vpcs[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  --region $REGION --query 'Subnets[].SubnetId' --output text)
SUBNETS_CSV=$(echo $SUBNETS | tr ' ' ',')
echo "    VPC=$VPC_ID  Subnets=$SUBNETS_CSV"

echo "==> Creating security groups..."
# ALB SG: allow HTTP (port 80) from anywhere on the internet.
ALB_SG=$(aws ec2 create-security-group --group-name docex-alb-sg \
  --description "DOCex ALB" --vpc-id $VPC_ID --region $REGION \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $ALB_SG \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $REGION >/dev/null

# API SG: allow port 8000 ONLY from the ALB's security group (not the public).
API_SG=$(aws ec2 create-security-group --group-name docex-api-sg \
  --description "DOCex API tasks" --vpc-id $VPC_ID --region $REGION \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $API_SG \
  --protocol tcp --port 8000 --source-group $ALB_SG --region $REGION >/dev/null
echo "    ALB_SG=$ALB_SG  API_SG=$API_SG"

echo "==> Creating load balancer..."
ALB_ARN=$(aws elbv2 create-load-balancer --name docex-alb \
  --subnets $SUBNETS --security-groups $ALB_SG --region $REGION \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

echo "==> Creating target group (health check: /health)..."
TG_ARN=$(aws elbv2 create-target-group --name docex-api-tg \
  --protocol HTTP --port 8000 --vpc-id $VPC_ID --target-type ip \
  --health-check-path /health --region $REGION \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "==> Creating listener (ALB :80 -> target group)..."
aws elbv2 create-listener --load-balancer-arn $ALB_ARN \
  --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN \
  --region $REGION >/dev/null

echo "==> Creating ECS service..."
aws ecs create-service \
  --cluster docex-cluster \
  --service-name docex-api \
  --task-definition docex-api \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_CSV],securityGroups=[$API_SG],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=docex-api,containerPort=8000" \
  --health-check-grace-period-seconds 90 \
  --region $REGION >/dev/null

ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN \
  --region $REGION --query 'LoadBalancers[0].DNSName' --output text)

# Save everything for later (web service wiring, cleanup, Terraform reference).
cat > deploy/api-service-ids.txt <<EOF
VPC_ID=$VPC_ID
SUBNETS_CSV=$SUBNETS_CSV
ALB_SG=$ALB_SG
API_SG=$API_SG
ALB_ARN=$ALB_ARN
TG_ARN=$TG_ARN
ALB_DNS=$ALB_DNS
EOF

echo ""
echo "==> DONE. Once the task is healthy (1-3 min), your API will be at:"
echo "    http://$ALB_DNS/health"
echo "    http://$ALB_DNS/docs"
echo "    (IDs saved to deploy/api-service-ids.txt)"
