# ── Guardrail rules for CloudFormation templates (ADR-0004) ───
# Each template rule takes a parsed template (dict) and returns a list of
# problem strings; an empty list means the template passes.
import re                                                               # regular expressions
import subprocess                                                       # asks git which files are tracked
from pathlib import Path                                                # file paths

import yaml                                                             # YAML parser (PyYAML)

REPO_ROOT = Path(__file__).resolve().parents[1]                         # repository root
INFRA_FOLDER = REPO_ROOT / "infra"                                      # repo-root/infra
TEXT_SUFFIXES = {".yaml", ".yml", ".toml", ".json", ".md", ".py", ".sql", ".txt", ".cfg", ".ini"}  # text files scanned for account IDs
TEXT_NAMES = {"Makefile", ".cfnlintrc", ".gitignore"}                   # suffix-less text files scanned too
ACCOUNT_ID = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")                # exactly 12 digits in a row
BLOCK_FLAGS = ["BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"]  # all four must be true
NAME_PROPERTIES = ["BucketName", "FunctionName", "Name", "TableName", "StreamName", "DeliveryStreamName"]  # explicit-name properties
IAM_NAME_PROPERTIES = {                                                 # IAM names that need CAPABILITY_NAMED_IAM
    "AWS::IAM::Role": "RoleName",                                       # roles
    "AWS::IAM::ManagedPolicy": "ManagedPolicyName",                     # customer managed policies
    "AWS::IAM::Group": "GroupName",                                     # groups
    "AWS::IAM::InstanceProfile": "InstanceProfileName",                 # instance profiles
}
BROAD_MANAGED_POLICY = re.compile(r"(AdministratorAccess|PowerUserAccess|FullAccess)")  # AWS managed policies too broad to attach
SAM_POLICY_TYPES = {"AWS::Serverless::Function", "AWS::Serverless::StateMachine"}  # SAM types with a Policies shorthand


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


# ── Account IDs (every tracked text file in the repository) ───
def tracked_text_files(root: Path) -> list[Path]:                       # files git tracks, text types only
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True).stdout  # NUL-separated paths
    paths = [root / name for name in listing.split("\0") if name]       # absolute paths, empty entries dropped
    return sorted(path for path in paths if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES)  # text files, stable order


def account_id_problems(root: Path) -> list[str]:                       # scan committed files for 12-digit numbers
    problems = []                                                       # collected problems
    for path in tracked_text_files(root):                               # untracked build output is never scanned
        if path.is_file() and ACCOUNT_ID.search(path.read_text(encoding="utf-8", errors="ignore")):  # tracked and still on disk
            problems.append(f"{path.relative_to(root).as_posix()}: 12-digit number (possible AWS account ID)")  # report relative path
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


def _is_everyone(principal) -> bool:                                    # Principal "*" or {"AWS": "*"}
    if principal == "*":                                                # bare wildcard
        return True                                                     # everyone
    return isinstance(principal, dict) and "*" in _as_list(principal.get("AWS"))  # AWS-wildcard form


def _covers_objects(resource) -> bool:                                  # does a Resource entry include the bucket's objects?
    text = resource.get("Fn::Sub") if isinstance(resource, dict) else resource  # !Sub text or a plain string
    text = text[0] if isinstance(text, list) else text                  # !Sub list form: first item is the text
    return isinstance(text, str) and (text == "*" or text.endswith("/*"))  # "*" or ".../*"


def _denies_plain_http(statement) -> bool:                              # a full TLS-only deny statement
    if not isinstance(statement, dict) or statement.get("Effect") != "Deny":  # only Deny statements count
        return False                                                    # anything else is not a TLS deny
    condition = (statement.get("Condition") or {}).get("Bool") or {}    # Bool condition block
    return (str(condition.get("aws:SecureTransport")).lower() == "false"  # only when TLS is not used...
            and _is_everyone(statement.get("Principal"))                # ...for every caller...
            and any(action in ("*", "s3:*") for action in _as_list(statement.get("Action")))  # ...every S3 action...
            and any(_covers_objects(resource) for resource in _as_list(statement.get("Resource"))))  # ...including objects


def insecure_transport_problems(template: dict) -> list[str]:           # every bucket has a TLS-only deny
    covered = set()                                                     # buckets with a TLS deny policy
    for body in _resources(template).values():                          # every resource
        if (body or {}).get("Type") != "AWS::S3::BucketPolicy":         # only bucket policies
            continue                                                    # skip others
        target = ((body.get("Properties") or {}).get("Bucket") or {})   # which bucket the policy is for
        if any(_denies_plain_http(statement) for statement in _statements(body.get("Properties"))):  # has a full TLS deny
            if isinstance(target, dict) and "Ref" in target:            # attached with !Ref Bucket
                covered.add(target["Ref"])                              # mark that bucket covered
    return [f"{name}: no bucket policy denying requests without TLS" for name in _buckets(template) if name not in covered]  # uncovered buckets


# ── IAM rules ─────────────────────────────────────────────────
def _allow_statements(body):                                            # every Allow statement under a resource
    return [statement for statement in _statements(body) if isinstance(statement, dict) and statement.get("Effect") == "Allow"]  # skip nulls and Denys


def wildcard_action_problems(template: dict) -> list[str]:              # no admin-style or near-admin grants
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        for statement in _allow_statements(body):                       # each Allow statement inside it
            actions = _as_list(statement.get("Action"))                 # granted actions
            if "*" in actions:                                          # every action on everything
                problems.append(f"{name}: Allow statement with Action '*'")  # report
            elif "NotAction" in statement or "NotResource" in statement:  # allow-by-exclusion grants
                problems.append(f"{name}: Allow statement with NotAction/NotResource")  # report
            elif "*" in _as_list(statement.get("Resource")) and any(isinstance(action, str) and action.endswith(":*") for action in actions):  # service-wide on all resources
                problems.append(f"{name}: Allow statement with a service-wide action on Resource '*'")  # report
    return problems                                                     # empty when no broad grants


def broad_managed_policy_problems(template: dict) -> list[str]:        # no AdministratorAccess / PowerUserAccess / *FullAccess
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        properties = (body or {}).get("Properties") or {}               # its properties
        attached = _as_list(properties.get("ManagedPolicyArns") or [])  # IAM role / group / user attachments
        if (body or {}).get("Type") in SAM_POLICY_TYPES:                # SAM Policies shorthand: string or list
            attached += _as_list(properties.get("Policies") or [])      # policy names or ARNs mixed with statements
        problems += [f"{name}: broad AWS managed policy {policy}" for policy in attached if isinstance(policy, str) and BROAD_MANAGED_POLICY.search(policy)]  # report each
    return problems                                                     # empty when no broad managed policies


def public_principal_problems(template: dict) -> list[str]:            # nothing callable or readable by everyone
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        kind = (body or {}).get("Type")                                 # resource type
        properties = (body or {}).get("Properties") or {}               # its properties
        if kind == "AWS::Lambda::Permission" and properties.get("Principal") == "*":  # anyone may invoke
            problems.append(f"{name}: Lambda permission for Principal '*'")  # report
        url = properties if kind == "AWS::Lambda::Url" else properties.get("FunctionUrlConfig") if kind == "AWS::Serverless::Function" else None  # function URL settings
        if isinstance(url, dict) and url.get("AuthType") == "NONE":     # unauthenticated URL
            problems.append(f"{name}: function URL with AuthType NONE")  # report
        if any(_is_everyone(statement.get("Principal")) for statement in _allow_statements(body)):  # resource policy open to all
            problems.append(f"{name}: Allow statement with Principal '*'")  # report
    return problems                                                     # empty when nothing is public


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


# ── T1a rules: Glue jobs, Lambda concurrency, catalog names ───
ATHENA_NAME = re.compile(r"^[a-z][a-z0-9_]*$")                          # Athena-safe database/table name
LAMBDA_TYPES = {"AWS::Serverless::Function", "AWS::Lambda::Function"}   # function resource types


def glue_job_problems(template: dict) -> list[str]:                     # bounded, self-contained Glue jobs
    problems = []                                                       # collected problems
    for name, body in _resources(template).items():                     # each resource
        if (body or {}).get("Type") != "AWS::Glue::Job":                # Glue jobs only
            continue                                                    # skip others
        properties = body.get("Properties") or {}                       # job settings
        timeout = properties.get("Timeout")                             # minutes
        if not isinstance(timeout, int) or timeout > 30:                # default is 480 min on Glue 5.0+
            problems.append(f"{name}: Timeout must be set and at most 30 minutes")  # report
        if "--TempDir" not in (properties.get("DefaultArguments") or {}):  # no temp path of our own
            problems.append(f"{name}: DefaultArguments has no --TempDir (Glue may create its own temp bucket)")  # report
    return problems                                                     # empty when every job is bounded


def lambda_concurrency_problems(template: dict) -> list[str]:           # every function has a concurrency cap
    return [f"{name}: ReservedConcurrentExecutions not set" for name, body in _resources(template).items()  # report each
            if (body or {}).get("Type") in LAMBDA_TYPES and "ReservedConcurrentExecutions" not in (body.get("Properties") or {})]  # uncapped functions


def catalog_name_problems(template: dict) -> list[str]:                 # Glue catalog names Athena can use
    problems = []                                                       # collected problems
    nested = {"AWS::Glue::Database": "DatabaseInput", "AWS::Glue::Table": "TableInput"}  # where the name lives
    for name, body in _resources(template).items():                     # each resource
        holder = nested.get((body or {}).get("Type"))                   # DatabaseInput / TableInput, if a catalog object
        if not holder:                                                  # not a catalog object
            continue                                                    # skip
        value = ((body.get("Properties") or {}).get(holder) or {}).get("Name")  # the configured name
        if not isinstance(value, str) or not ATHENA_NAME.match(value):  # missing, !Sub, or has hyphens/upper case
            problems.append(f"{name}: {holder}.Name must be set, lowercase letters, digits or _")  # report
    return problems                                                     # empty when every name is Athena-safe


ALL_TEMPLATE_RULES = [                                                  # every rule that takes a template
    unencrypted_bucket_problems,                                        # encryption at rest
    public_bucket_problems,                                             # no public access
    insecure_transport_problems,                                        # TLS only
    wildcard_action_problems,                                           # no Action "*", NotAction or service-wide "*"
    broad_managed_policy_problems,                                      # no admin/full-access managed policies
    public_principal_problems,                                          # no public principals or open URLs
    iam_user_problems,                                                  # no IAM users or keys
    named_iam_problems,                                                 # no explicit IAM names
    unscoped_name_problems,                                             # stack-scoped names
    glue_job_problems,                                                  # bounded, self-contained Glue jobs
    lambda_concurrency_problems,                                        # every function has a concurrency cap
    catalog_name_problems,                                              # Athena-compatible catalog names
]
