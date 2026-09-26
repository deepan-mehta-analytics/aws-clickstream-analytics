# ── Guardrail rules for CloudFormation templates (ADR-0004) ───
# Each template rule takes a parsed template (dict) and returns a list of
# problem strings; an empty list means the template passes.
import re                                                               # regular expressions
from pathlib import Path                                                # file paths

import yaml                                                             # YAML parser (PyYAML)

INFRA_FOLDER = Path(__file__).resolve().parents[1] / "infra"            # repo-root/infra
TEXT_SUFFIXES = {".yaml", ".yml", ".toml", ".json", ".md"}              # files scanned for account IDs
ACCOUNT_ID = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")                # exactly 12 digits in a row
BLOCK_FLAGS = ["BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"]  # all four must be true
NAME_PROPERTIES = ["BucketName", "FunctionName", "Name", "TableName", "StreamName", "DeliveryStreamName"]  # explicit-name properties
IAM_NAME_PROPERTIES = {"AWS::IAM::Role": "RoleName", "AWS::IAM::ManagedPolicy": "ManagedPolicyName"}  # names that need NAMED_IAM


# ── Loading ───────────────────────────────────────────────────
class TemplateLoader(yaml.SafeLoader):                                  # safe loader that understands CloudFormation tags
    pass                                                                # behaviour added by the constructor below


def _short_tag(loader, suffix, node):                                   # turn !Ref / !Sub / !GetAtt ... into long form
    if isinstance(node, yaml.ScalarNode):                               # !Ref Name
        value = loader.construct_scalar(node)                           # plain string
    elif isinstance(node, yaml.SequenceNode):                           # !Sub [text, {vars}]
        value = loader.construct_sequence(node, deep=True)              # list
    else:                                                               # mapping form
        value = loader.construct_mapping(node, deep=True)               # dict
    if suffix == "Ref":                                                 # !Ref is not an Fn:: function
        return {"Ref": value}                                           # {"Ref": "Name"}
    if suffix == "GetAtt" and isinstance(value, str):                   # !GetAtt Bucket.Arn
        return {"Fn::GetAtt": value.split(".", 1)}                      # ["Bucket", "Arn"]
    return {f"Fn::{suffix}": value}                                     # every other tag, e.g. {"Fn::Sub": ...}


TemplateLoader.add_multi_constructor("!", _short_tag)                   # handle every tag starting with "!"


def load_template(path: Path) -> dict:                                  # parse one template file
    # TemplateLoader extends SafeLoader: "!!python/..." tags are not "!"-prefixed after expansion, so they still hit SafeLoader and are rejected
    return yaml.load(path.read_text(encoding="utf-8"), Loader=TemplateLoader) or {}  # empty file → {}


def template_paths() -> list[Path]:                                     # every tier template, sorted
    return sorted(INFRA_FOLDER.glob("*/template.yaml"))                 # one template per stack folder


# ── Helpers ───────────────────────────────────────────────────
def _resources(template: dict) -> dict:                                 # the Resources mapping, never None
    return (template or {}).get("Resources") or {}                      # tolerate missing or empty sections


def _as_list(value) -> list:                                            # CloudFormation allows a value or a list
    return value if isinstance(value, list) else [value]                # always a list


def _statements(node):                                                  # every policy statement anywhere under node
    if isinstance(node, dict):                                          # mappings may hold a Statement key
        if "Statement" in node:                                         # a policy document
            yield from _as_list(node["Statement"])                      # single mapping or list
        for child in node.values():                                     # keep searching deeper
            yield from _statements(child)                               # recurse
    elif isinstance(node, list):                                        # lists: search every item
        for child in node:                                              # each item
            yield from _statements(child)                               # recurse


def _buckets(template: dict) -> dict:                                   # logical name → bucket resource
    return {name: body for name, body in _resources(template).items() if (body or {}).get("Type") == "AWS::S3::Bucket"}  # S3 buckets only


# ── Account IDs (every text file under infra/) ────────────────
def account_id_problems(folder: Path) -> list[str]:                     # scan a folder for 12-digit numbers
    problems = []                                                       # collected problems
    for path in sorted(folder.rglob("*")):                              # every file, stable order
        if path.is_file() and path.suffix in TEXT_SUFFIXES and ACCOUNT_ID.search(path.read_text(encoding="utf-8")):  # text file with 12 digits
            problems.append(f"{path.relative_to(folder).as_posix()}: 12-digit number (possible AWS account ID)")  # report relative path
    return problems                                                     # empty when clean


# ── Bucket rules ──────────────────────────────────────────────
def unencrypted_bucket_problems(template: dict) -> list[str]:           # encryption at rest on every bucket
    problems = []                                                       # collected problems
    for name, bucket in _buckets(template).items():                     # each bucket
        rules = ((bucket.get("Properties") or {}).get("BucketEncryption") or {}).get("ServerSideEncryptionConfiguration") or []  # encryption rules
        if not rules or not all((rule.get("ServerSideEncryptionByDefault") or {}).get("SSEAlgorithm") for rule in rules):  # missing algorithm
            problems.append(f"{name}: no BucketEncryption with an SSEAlgorithm")  # report
    return problems                                                     # empty when every bucket is encrypted


def public_bucket_problems(template: dict) -> list[str]:                # all four Block Public Access flags on
    problems = []                                                       # collected problems
    for name, bucket in _buckets(template).items():                     # each bucket
        block = (bucket.get("Properties") or {}).get("PublicAccessBlockConfiguration") or {}  # block settings
        problems += [f"{name}: {flag} is not true" for flag in BLOCK_FLAGS if block.get(flag) is not True]  # each missing flag
    return problems                                                     # empty when every bucket is private


def insecure_transport_problems(template: dict) -> list[str]:           # every bucket has a TLS-only deny
    covered = set()                                                     # buckets with a TLS deny policy
    for body in _resources(template).values():                          # every resource
        if (body or {}).get("Type") != "AWS::S3::BucketPolicy":         # only bucket policies
            continue                                                    # skip others
        target = ((body.get("Properties") or {}).get("Bucket") or {})   # which bucket the policy is for
        for statement in _statements(body.get("Properties")):           # each statement
            condition = ((statement or {}).get("Condition") or {}).get("Bool") or {}  # Bool condition block
            if statement.get("Effect") == "Deny" and str(condition.get("aws:SecureTransport")).lower() == "false":  # TLS deny
                if isinstance(target, dict) and "Ref" in target:        # attached with !Ref Bucket
                    covered.add(target["Ref"])                          # mark that bucket covered
    return [f"{name}: no bucket policy denying requests without TLS" for name in _buckets(template) if name not in covered]  # uncovered buckets


# ── IAM rules ─────────────────────────────────────────────────
def wildcard_action_problems(template: dict) -> list[str]:              # no Allow with Action "*"
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        for statement in _statements(body):                             # each statement inside it
            if (statement or {}).get("Effect") == "Allow" and "*" in _as_list(statement.get("Action")):  # admin-style grant
                problems.append(f"{name}: Allow statement with Action '*'")  # report
    return problems                                                     # empty when no wildcard grants


def iam_user_problems(template: dict) -> list[str]:                     # no IAM users or access keys
    forbidden = {"AWS::IAM::User", "AWS::IAM::AccessKey"}               # long-term credentials
    return [f"{name}: {body['Type']} is not allowed" for name, body in _resources(template).items() if (body or {}).get("Type") in forbidden]  # report each


def named_iam_problems(template: dict) -> list[str]:                    # IAM names left to CloudFormation
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        prop = IAM_NAME_PROPERTIES.get((body or {}).get("Type"))        # name property for this IAM type, if any
        if prop and prop in ((body.get("Properties") or {})):           # explicit IAM name set
            problems.append(f"{name}: {prop} set (needs CAPABILITY_NAMED_IAM; let CloudFormation name it)")  # report
    return problems                                                     # empty when no IAM names set


# ── Naming rule ───────────────────────────────────────────────
def unscoped_name_problems(template: dict) -> list[str]:                # explicit names must include the stack name
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        properties = (body or {}).get("Properties") or {}               # its properties
        for prop in NAME_PROPERTIES:                                    # each explicit-name property
            if prop not in properties:                                  # not set: CloudFormation generates a name
                continue                                                # nothing to check
            value = properties[prop]                                    # the configured name
            text = value.get("Fn::Sub") if isinstance(value, dict) else None  # !Sub text or [text, vars]
            text = text[0] if isinstance(text, list) else text          # list form: first item is the text
            if not isinstance(text, str) or "${AWS::StackName}" not in text:  # not built from the stack name
                problems.append(f"{name}: {prop} is not !Sub with ${{AWS::StackName}}")  # report
    return problems                                                     # empty when every name is stack-scoped


ALL_TEMPLATE_RULES = [                                                  # every rule that takes a template
    unencrypted_bucket_problems,                                        # encryption at rest
    public_bucket_problems,                                             # no public access
    insecure_transport_problems,                                        # TLS only
    wildcard_action_problems,                                           # no Action "*"
    iam_user_problems,                                                  # no IAM users or keys
    named_iam_problems,                                                 # no explicit IAM names
    unscoped_name_problems,                                             # stack-scoped names
]
