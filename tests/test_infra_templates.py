# ── Tests: infrastructure template guardrails (ADR-0004) ──────
from pathlib import Path                                                # file paths

from infra_rules import (                                               # rules under test
    account_id_problems,                                                # no 12-digit numbers
    iam_user_problems,                                                  # no IAM users or keys
    insecure_transport_problems,                                        # TLS-only bucket policies
    named_iam_problems,                                                 # IAM names left to CloudFormation
    public_bucket_problems,                                             # Block Public Access on
    unencrypted_bucket_problems,                                        # encryption at rest on
    unscoped_name_problems,                                             # names built from the stack name
    wildcard_action_problems,                                           # no Action "*"
    ALL_TEMPLATE_RULES,                                                 # every template rule
)

# ── Hand-made templates ───────────────────────────────────────
GOOD_BUCKET = {                                                         # a bucket that passes every bucket rule
    "Type": "AWS::S3::Bucket",                                          # S3 bucket resource
    "Properties": {                                                     # bucket settings
        "BucketEncryption": {"ServerSideEncryptionConfiguration": [     # encryption at rest
            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},  # SSE-S3
        "PublicAccessBlockConfiguration": {                             # all four public-access blocks
            "BlockPublicAcls": True, "BlockPublicPolicy": True,         # block ACLs and public policies
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True,    # ignore ACLs, restrict public buckets
        },
    },
}
TLS_POLICY = {                                                          # bucket policy denying plain HTTP
    "Type": "AWS::S3::BucketPolicy",                                    # bucket policy resource
    "Properties": {                                                     # policy settings
        "Bucket": {"Ref": "DataBucket"},                                # attached to DataBucket
        "PolicyDocument": {"Statement": [{                              # one statement
            "Effect": "Deny", "Principal": "*", "Action": "s3:*",       # deny everything to everyone...
            "Resource": "*",                                            # ...on any object
            "Condition": {"Bool": {"aws:SecureTransport": "false"}},    # ...when not using TLS
        }]},
    },
}


def good_template():                                                    # fresh passing template per test
    return {"Resources": {"DataBucket": GOOD_BUCKET, "DataBucketPolicy": TLS_POLICY}}  # bucket + its TLS policy


# ── Each rule accepts the good template ───────────────────────
def test_good_template_passes_every_rule():                             # baseline: no false alarms
    for rule in ALL_TEMPLATE_RULES:                                     # every template rule
        assert rule(good_template()) == [], rule.__name__               # no problems reported


# ── Each rule rejects a matching bad template ─────────────────
def test_encryption_rule_flags_bucket_without_encryption():             # missing BucketEncryption
    template = good_template()                                          # start from a passing template
    template["Resources"]["DataBucket"] = {"Type": "AWS::S3::Bucket", "Properties": {  # bucket with no encryption
        "PublicAccessBlockConfiguration": GOOD_BUCKET["Properties"]["PublicAccessBlockConfiguration"]}}  # still private
    assert unencrypted_bucket_problems(template) == ["DataBucket: no BucketEncryption with an SSEAlgorithm"]  # flagged


def test_public_rule_flags_missing_block_flag():                        # one of four flags off
    template = good_template()                                          # start from a passing template
    bucket = {"Type": "AWS::S3::Bucket", "Properties": dict(GOOD_BUCKET["Properties"])}  # copy the bucket
    bucket["Properties"]["PublicAccessBlockConfiguration"] = {          # RestrictPublicBuckets missing
        "BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True}  # only three flags
    template["Resources"]["DataBucket"] = bucket                        # swap in the weak bucket
    assert public_bucket_problems(template) == ["DataBucket: RestrictPublicBuckets is not true"]  # flagged


def test_tls_rule_flags_bucket_without_policy():                        # no bucket policy at all
    template = {"Resources": {"DataBucket": GOOD_BUCKET}}               # bucket only
    assert insecure_transport_problems(template) == ["DataBucket: no bucket policy denying requests without TLS"]  # flagged


def test_tls_rule_ignores_policy_for_other_bucket():                    # Review Focus 3
    template = {"Resources": {"DataBucket": GOOD_BUCKET, "OtherPolicy": {  # policy exists...
        "Type": "AWS::S3::BucketPolicy",                                # bucket policy resource
        "Properties": {"Bucket": {"Ref": "SomeOtherBucket"},            # ...but for another bucket
                       "PolicyDocument": TLS_POLICY["Properties"]["PolicyDocument"]}}}}  # same TLS statement
    assert insecure_transport_problems(template) == ["DataBucket: no bucket policy denying requests without TLS"]  # still flagged


def test_wildcard_rule_flags_action_star():                             # Allow with Action "*"
    template = {"Resources": {"WorkerRole": {"Type": "AWS::IAM::Role", "Properties": {"Policies": [{  # a role policy
        "PolicyName": "everything",                                     # inline policy name
        "PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": ["*"], "Resource": "*"}]}}]}}}}  # admin grant
    assert wildcard_action_problems(template) == ["WorkerRole: Allow statement with Action '*'"]  # flagged


def test_wildcard_rule_handles_single_statement_and_string_action():    # Review Focus 1
    template = {"Resources": {"WorkerPolicy": {"Type": "AWS::IAM::ManagedPolicy", "Properties": {  # managed policy
        "PolicyDocument": {"Statement": {"Effect": "Allow", "Action": "*", "Resource": "*"}}}}}}  # single mapping, string action
    assert wildcard_action_problems(template) == ["WorkerPolicy: Allow statement with Action '*'"]  # flagged


def test_iam_user_rule_flags_user_and_key():                            # IAM users and access keys
    template = {"Resources": {"Person": {"Type": "AWS::IAM::User"}, "PersonKey": {"Type": "AWS::IAM::AccessKey"}}}  # both forbidden
    assert iam_user_problems(template) == ["Person: AWS::IAM::User is not allowed", "PersonKey: AWS::IAM::AccessKey is not allowed"]  # both flagged


def test_named_iam_rule_flags_role_name():                              # Review Focus 2
    template = {"Resources": {"WorkerRole": {"Type": "AWS::IAM::Role", "Properties": {"RoleName": "worker"}}}}  # explicit role name
    assert named_iam_problems(template) == ["WorkerRole: RoleName set (needs CAPABILITY_NAMED_IAM; let CloudFormation name it)"]  # flagged


def test_unscoped_name_rule_flags_fixed_name():                         # name not built from the stack name
    template = {"Resources": {"Worker": {"Type": "AWS::Serverless::Function", "Properties": {"FunctionName": "worker"}}}}  # fixed name
    assert unscoped_name_problems(template) == ["Worker: FunctionName is not !Sub with ${AWS::StackName}"]  # flagged


def test_unscoped_name_rule_accepts_stack_scoped_name():                # !Sub with the stack name passes
    template = {"Resources": {"Worker": {"Type": "AWS::Serverless::Function", "Properties": {  # SAM function
        "FunctionName": {"Fn::Sub": "${AWS::StackName}-worker"}}}}}     # stack-scoped name
    assert unscoped_name_problems(template) == []                       # accepted


def test_account_id_rule_scans_every_infra_text_file(tmp_path: Path):   # Review Focus 4
    (tmp_path / "README.md").write_text("Sign in at https://123456789012.signin.aws.amazon.com\n", encoding="utf-8")  # leaked ID in docs
    (tmp_path / "ok.toml").write_text('region = "ap-south-1"\n', encoding="utf-8")  # clean file
    assert account_id_problems(tmp_path) == ["README.md: 12-digit number (possible AWS account ID)"]  # only the leak flagged


def test_rules_tolerate_empty_template():                               # Review Focus 5
    for rule in ALL_TEMPLATE_RULES:                                     # every template rule
        assert rule({}) == [], rule.__name__                            # empty template: nothing to flag, no crash
        assert rule({"Resources": None}) == [], rule.__name__           # empty Resources section: same
