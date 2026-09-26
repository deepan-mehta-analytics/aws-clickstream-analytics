# infra/

Empty for now. The tool is decided: AWS SAM-extended CloudFormation, one
stack per tier ([ADR-0004](../docs/adr/0004-iac-sam-cloudformation.md)).
The first stack (an artifacts bucket) and the template guardrail tests come
next. IAM for every tier is applied by the account owner, never by an
automated agent.
