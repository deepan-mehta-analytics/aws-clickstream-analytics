# ── Tests: infrastructure template guardrails (ADR-0004) ──────
from pathlib import Path                                                # file paths

import pytest                                                           # parametrize over real templates

import subprocess                                                       # builds a throwaway git repo for the account-ID test

from infra_rules import (                                               # rules and helpers under test
    ALL_TEMPLATE_RULES,                                                 # every template rule
    REPO_ROOT,                                                          # repository root
    account_id_problems,                                                # no 12-digit numbers
    broad_managed_policy_problems,                                      # no admin/full-access managed policies
    public_principal_problems,                                          # no public principals or open function URLs
    iam_user_problems,                                                  # no IAM users or keys
    insecure_transport_problems,                                        # TLS-only bucket policies
    load_template,                                                      # parse a real template
    named_iam_problems,                                                  # IAM names left to CloudFormation
    public_bucket_problems,                                             # Block Public Access on
    template_paths,                                                     # every infra/*/template.yaml
    unencrypted_bucket_problems,                                        # encryption at rest on
    unscoped_name_problems,                                             # names built from the stack name
    wildcard_action_problems,                                           # no Action "*"
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


def test_account_id_rule_scans_tracked_files_only(tmp_path: Path):      # Review Focus 4 + final review I4
    fake_id = "1234567" + "89012"                                       # built at runtime so this test file holds no 12-digit literal
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)     # throwaway repository
    (tmp_path / "README.md").write_text(f"Sign in at https://{fake_id}.signin.aws.amazon.com\n", encoding="utf-8")  # leaked ID in docs
    (tmp_path / "ok.toml").write_text('region = "ap-south-1"\n', encoding="utf-8")  # clean file
    (tmp_path / ".aws-sam").mkdir()                                     # build output folder, never committed
    (tmp_path / ".aws-sam" / "vendored.json").write_text(f'{{"id": "{fake_id}"}}\n', encoding="utf-8")  # untracked 12 digits
    subprocess.run(["git", "add", "README.md", "ok.toml"], cwd=tmp_path, check=True)  # track only the two files
    assert account_id_problems(tmp_path) == ["README.md: 12-digit number (possible AWS account ID)"]  # untracked file ignored


def test_wildcard_rule_flags_not_action():                              # final review I1: NotAction is near-admin
    template = {"Resources": {"WorkerRole": {"Type": "AWS::IAM::Role", "Properties": {"Policies": [{"PolicyDocument": {  # role policy
        "Statement": [{"Effect": "Allow", "NotAction": "iam:*", "Resource": "*"}]}}]}}}}  # everything except IAM
    assert wildcard_action_problems(template) == ["WorkerRole: Allow statement with NotAction/NotResource"]  # flagged


def test_wildcard_rule_flags_service_wildcard_on_every_resource():      # final review I1: s3:* on "*"
    template = {"Resources": {"WorkerRole": {"Type": "AWS::IAM::Role", "Properties": {"Policies": [{"PolicyDocument": {  # role policy
        "Statement": [{"Effect": "Allow", "Action": ["s3:*"], "Resource": "*"}]}}]}}}}  # all S3 on every bucket
    assert wildcard_action_problems(template) == ["WorkerRole: Allow statement with a service-wide action on Resource '*'"]  # flagged


def test_broad_managed_policy_rule_flags_admin_and_full_access():       # final review I1: managed-policy shortcuts
    template = {"Resources": {                                          # three ways to attach a broad AWS policy
        "WorkerRole": {"Type": "AWS::IAM::Role", "Properties": {"ManagedPolicyArns": ["arn:aws:iam::aws:policy/AdministratorAccess"]}},  # role ARN
        "Loader": {"Type": "AWS::Serverless::Function", "Properties": {"Policies": "AmazonS3FullAccess"}},  # SAM string form
        "Reader": {"Type": "AWS::Serverless::Function", "Properties": {"Policies": ["PowerUserAccess"]}},  # SAM list form
    }}
    assert broad_managed_policy_problems(template) == [                 # all three flagged
        "WorkerRole: broad AWS managed policy arn:aws:iam::aws:policy/AdministratorAccess",  # admin
        "Loader: broad AWS managed policy AmazonS3FullAccess",          # full access
        "Reader: broad AWS managed policy PowerUserAccess",             # power user
    ]


def test_public_principal_rule_flags_open_access():                     # final review I2: public principals
    template = {"Resources": {                                          # four public-exposure patterns
        "OpenInvoke": {"Type": "AWS::Lambda::Permission", "Properties": {"Principal": "*"}},  # anyone may invoke
        "OpenUrl": {"Type": "AWS::Lambda::Url", "Properties": {"AuthType": "NONE"}},  # unauthenticated function URL
        "Loader": {"Type": "AWS::Serverless::Function", "Properties": {"FunctionUrlConfig": {"AuthType": "NONE"}}},  # SAM open URL
        "OpenQueue": {"Type": "AWS::SQS::QueuePolicy", "Properties": {"PolicyDocument": {"Statement": [  # resource policy
            {"Effect": "Allow", "Principal": {"AWS": "*"}, "Action": "sqs:SendMessage", "Resource": "*"}]}}},  # anyone may send
    }}
    assert public_principal_problems(template) == [                     # all four flagged
        "OpenInvoke: Lambda permission for Principal '*'",              # public invoke
        "OpenUrl: function URL with AuthType NONE",                     # open URL
        "Loader: function URL with AuthType NONE",                      # open SAM URL
        "OpenQueue: Allow statement with Principal '*'",                # public resource policy
    ]


def test_tls_rule_rejects_deny_limited_to_one_action():                 # final review I3: weak deny
    template = good_template()                                          # start from a passing template
    policy = template["Resources"]["DataBucketPolicy"] = {"Type": "AWS::S3::BucketPolicy", "Properties": {  # replace the policy
        "Bucket": {"Ref": "DataBucket"}, "PolicyDocument": {"Statement": [{  # same bucket...
            "Effect": "Deny", "Principal": "*", "Action": "s3:GetObject", "Resource": "*",  # ...but one action only
            "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}}}  # TLS condition
    assert policy["Type"] == "AWS::S3::BucketPolicy"                    # sanity: policy swapped in
    assert insecure_transport_problems(template) == ["DataBucket: no bucket policy denying requests without TLS"]  # flagged


def test_tls_rule_requires_objects_in_resource():                       # final review I3: bucket ARN only
    template = good_template()                                          # start from a passing template
    template["Resources"]["DataBucketPolicy"] = {"Type": "AWS::S3::BucketPolicy", "Properties": {  # replace the policy
        "Bucket": {"Ref": "DataBucket"}, "PolicyDocument": {"Statement": [{  # same bucket
            "Effect": "Deny", "Principal": "*", "Action": "s3:*",          # every action...
            "Resource": {"Fn::GetAtt": ["DataBucket", "Arn"]},           # ...but the bucket only, not its objects
            "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}}}  # TLS condition
    assert insecure_transport_problems(template) == ["DataBucket: no bucket policy denying requests without TLS"]  # flagged


def test_tls_rule_accepts_sub_object_arn():                             # the foundation template's form passes
    template = good_template()                                          # start from a passing template
    template["Resources"]["DataBucketPolicy"]["Properties"]["PolicyDocument"]["Statement"][0]["Resource"] = [  # bucket + objects
        {"Fn::GetAtt": ["DataBucket", "Arn"]}, {"Fn::Sub": "${DataBucket.Arn}/*"}]  # objects via !Sub
    assert insecure_transport_problems(template) == []                  # accepted


def test_named_iam_rule_flags_group_and_instance_profile():             # final review minor 1
    template = {"Resources": {                                          # two more NAMED_IAM types
        "Team": {"Type": "AWS::IAM::Group", "Properties": {"GroupName": "team"}},  # named group
        "Profile": {"Type": "AWS::IAM::InstanceProfile", "Properties": {"InstanceProfileName": "profile"}},  # named profile
    }}
    assert named_iam_problems(template) == [                            # both flagged
        "Team: GroupName set (needs CAPABILITY_NAMED_IAM; let CloudFormation name it)",  # group
        "Profile: InstanceProfileName set (needs CAPABILITY_NAMED_IAM; let CloudFormation name it)",  # profile
    ]


def test_rules_tolerate_null_statement():                               # final review minor 7
    template = good_template()                                          # start from a passing template
    template["Resources"]["DataBucketPolicy"]["Properties"]["PolicyDocument"]["Statement"] = [None] + [  # a null entry first
        dict(TLS_POLICY["Properties"]["PolicyDocument"]["Statement"][0])]  # then the real TLS deny
    for rule in ALL_TEMPLATE_RULES:                                     # every template rule
        assert rule(template) == [], rule.__name__                      # no crash, no false alarm


def test_rules_tolerate_empty_template():                               # Review Focus 5
    for rule in ALL_TEMPLATE_RULES:                                     # every template rule
        assert rule({}) == [], rule.__name__                            # empty template: nothing to flag, no crash
        assert rule({"Resources": None}) == [], rule.__name__           # empty Resources section: same


# ── Real templates under infra/ ───────────────────────────────
def test_at_least_one_template_exists():                                # guards the loop below from passing on nothing
    assert [path.parent.name for path in template_paths()] != [], "no infra/*/template.yaml found"  # at least one stack


@pytest.mark.parametrize("path", template_paths(), ids=lambda path: path.parent.name)  # one case per stack folder
def test_real_template_passes_every_rule(path):                         # every rule on every real template
    template = load_template(path)                                      # parse the template
    problems = [problem for rule in ALL_TEMPLATE_RULES for problem in rule(template)]  # run every rule
    assert problems == []                                               # no guardrail broken


def test_tracked_files_have_no_account_ids():                           # every committed text file in the repo
    assert account_id_problems(REPO_ROOT) == []                         # no 12-digit numbers anywhere
