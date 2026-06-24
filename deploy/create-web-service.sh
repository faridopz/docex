#!/usr/bin/env bash
#
# Creates the public-facing infrastructure for the DOCex WEB frontend on ECS
# Fargate — its own ALB, target group, security groups, and service. Mirrors
# create-api-service.sh but on port 3000 with a "/" health check.
#
# Run once, from the project root:  bash deploy/create-web-service.sh

set -euo pipefail
REGION=eu-west-1

echo "==> Looking up default VPC and subnets..."
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --region $REGION --query 'Vpcs[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  --region $REGION --query 'Subnets[].SubnetId' --output text)
SUBNETS_CSV=$(echo $SUBNETS | tr ' ' ',')

echo "==> Creating security groups..."
# Web ALB SG: allow HTTP (80) from the internet.
ALB_SG=$(aws ec2 create-security-group --group-name docex-web-alb-sg \
  --description "DOCex web ALB" --vpc-id $VPC_ID --region $REGION \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $ALB_SG \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $REGION >/dev/null

# Web task SG: allow 3000 ONLY from the web ALB.
WEB_SG=$(aws ec2 create-security-group --group-name docex-web-sg \
  --description "DOCex web tasks" --vpc-id $VPC_ID --region $REGION \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $WEB_SG \
  --protocol tcp --port 3000 --source-group $ALB_SG --region $REGION >/dev/null

echo "==> Creating load balancer..."
ALB_ARN=$(aws elbv2 create-load-balancer --name docex-web-alb \
  --subnets $SUBNETS --security-groups $ALB_SG --region $REGION \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

echo "==> Creating target group (health check: / , accept 200-399)..."
TG_ARN=$(aws elbv2 create-target-group --name docex-web-tg \
  --protocol HTTP --port 3000 --vpc-id $VPC_ID --target-type ip \
  --health-check-path / --matcher HttpCode=200-399 --region $REGION \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "==> Creating listener (ALB :80 -> target group)..."
aws elbv2 create-listener --load-balancer-arn $ALB_ARN \
  --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN \
  --region $REGION >/dev/null

echo "==> Creating ECS service..."
aws ecs create-service \
  --cluster docex-cluster \
  --service-name docex-web \
  --task-definition docex-web \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_CSV],securityGroups=[$WEB_SG],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=docex-web,containerPort=3000" \
  --health-check-grace-period-seconds 90 \
  --region $REGION >/dev/null

ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN \
  --region $REGION --query 'LoadBalancers[0].DNSName' --output text)

cat > deploy/web-service-ids.txt <<EOF
WEB_ALB_SG=$ALB_SG
WEB_SG=$WEB_SG
WEB_ALB_ARN=$ALB_ARN
WEB_TG_ARN=$TG_ARN
WEB_ALB_DNS=$ALB_DNS
EOF

echo ""
echo "==> DONE. Once healthy (1-3 min), your FRONTEND will be at:"
echo "    http://$ALB_DNS"
echo "    (IDs saved to deploy/web-service-ids.txt)"
