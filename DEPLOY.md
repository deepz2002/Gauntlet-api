# Production deployment design — AWS

Design only: no cloud resources have been deployed and no cloud spending is required
for this assignment. The shipped scanner reads a JSON snapshot; live collectors and
production authentication would be additional implementation work.

## Compute, database and networking

Run the existing API and frontend images on ECS Fargate behind an HTTPS Application
Load Balancer with ACM certificates. Route `/api/*` to the API and other paths to the
frontend. Replace the frontend's Compose-only `api` upstream with ECS service discovery
or a production Nginx configuration; Docker service names do not resolve automatically
on ECS. Keep tasks and encrypted RDS PostgreSQL in private subnets across two AZs.
Allow database connections only from the API security group, and application traffic
only from the load balancer. Publish no database/Adminer ports; Adminer is development-only.
Use controlled egress or VPC endpoints for ECR, logs and secrets. Enable automated RDS
backups, point-in-time recovery and restore drills; choose Multi-AZ for availability.

Initially run one API task because BackgroundTasks and startup recovery assume one
process. Apply migrations once as a dedicated release task before updating services;
do not let multiple replicas race to migrate. Inject the database URL through Secrets
Manager and use TLS with certificate verification to RDS. Use separate task execution,
application, migration and deployment roles. Limit secrets access to the required ARN
(and KMS decrypt permission only when needed). Add authentication and account-level
authorization before exposing inventory or findings outside a trusted environment.

## CI deployment and operations

After lint, types, tests, image builds and smoke checks pass, a protected release
workflow would request a GitHub OIDC token and assume a restricted deployment role.
Constrain trust to the exact repository and protected branch/environment, with audience
`sts.amazonaws.com`. Permit ECR publishing and ECS deployment only for this application;
restrict `iam:PassRole` to its task roles. Store no long-lived AWS keys in GitHub.
Use immutable commit/digest image references and an ECS deployment circuit breaker for
rollback. This deployment workflow is a design proposal, not part of the local CI file.
See [GitHub's AWS OIDC guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

Send structured application logs and container output to CloudWatch with scan IDs,
retention limits and no credentials. Alarm on API errors, task restarts, failed/stuck
scans and database saturation. Before scaling the API, move execution to a durable
queue/worker model with job ownership, retries and idempotent writes; replace global
startup failure recovery with leases/heartbeats. Completed findings stay transactional
and persisted. Restarted jobs must not duplicate findings.

## Least-privilege live-scanner access

The current snapshot mode needs none of these permissions. A future collector would
assume a read-only role in each approved account through tightly scoped cross-account
trust, then normalize responses into the existing check interface.

| Checks | Read-only AWS actions |
| --- | --- |
| S3 public-access block | `s3:GetBucketPublicAccessBlock`; `s3:ListAllMyBuckets` only for discovery; `s3:GetBucketLocation` for region metadata |
| Security groups | `ec2:DescribeSecurityGroups` |
| Console MFA | `iam:ListUsers`, `iam:GetLoginProfile`, `iam:ListMFADevices` |
| Access-key age | `iam:ListUsers`, `iam:ListAccessKeys` (creation time; no key secrets) |
| RDS public accessibility | `rds:DescribeDBInstances` |

Scope bucket/user/database ARNs where supported. For discovery operations requiring
`Resource: "*"`, restrict the target account and allowed regions where supported.
No remediation, object reads, password access or access-key creation is needed.
[S3 action reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3.html),
[IAM](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsidentityandaccessmanagementiam.html),
[EC2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonec2.html),
[RDS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonrds.html).

For Azure, use workload identity federation and a custom role scoped to approved
subscriptions/resource groups with `Microsoft.Storage/storageAccounts/read` and
`Microsoft.Network/networkSecurityGroups/read`, not storage key access or write roles.
[Storage permissions](https://learn.microsoft.com/en-us/azure/role-based-access-control/permissions/storage),
[Networking permissions](https://learn.microsoft.com/en-us/azure/role-based-access-control/permissions/networking).

For GCP, use Workload Identity Federation/service-account impersonation with a custom
role containing `storage.buckets.get`, `storage.buckets.getIamPolicy`, and
`compute.firewalls.list`; add `storage.buckets.list` only for bucket discovery.
Scope to the approved projects/buckets, with no object access or policy writes.
[Storage permissions](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions),
[Firewall API](https://cloud.google.com/compute/docs/reference/rest/v1/firewalls/list).
