"""검토할 CloudFormation JSON만 생성한다. AWS 실행 없음. 작성자: 김진우."""
import json
from pathlib import Path

ACCOUNT = "577638373354"
REGION = "ap-northeast-2"
INSTANCE = f"arn:aws:ec2:{REGION}:{ACCOUNT}:instance/i-055b8632e5b93fd96"
REPOSITORY = f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/heapy-fastapi"
DOCUMENT = f"arn:aws:ssm:{REGION}:{ACCOUNT}:document/heapy-fastapi-dev-deploy"


def statement(actions, resources):
    return {"Effect": "Allow", "Action": actions, "Resource": resources}


def template():
    pull = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
    policy = {"Version": "2012-10-17", "Statement": [
        statement(["ecr:GetAuthorizationToken"], "*"),
        statement(pull + ["ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages"], REPOSITORY),
        statement(["ssm:SendCommand"], [INSTANCE, DOCUMENT]),
        statement(["ssm:GetCommandInvocation"], "*"),
    ]}
    command = {"schemaVersion": "2.2", "description": "FastAPI 개발 배포 전용. 작성자: 김진우",
               "parameters": {"ImageDigest": {"type": "String", "allowedPattern": "^sha256:[a-f0-9]{64}$", "interpolationType": "ENV_VAR"}},
               "mainSteps": [{"action": "aws:runShellScript", "name": "deploy", "inputs": {
                   "timeoutSeconds": "900", "runCommand": ["bash <<'HEAPY_DEPLOY_SCRIPT'\n" + Path(__file__).with_name("deploy.sh").read_text(encoding="utf-8") + "\nHEAPY_DEPLOY_SCRIPT"]}}]}
    return {"AWSTemplateFormatVersion": "2010-09-09", "Description": "HEAPY FastAPI 개발 배포. 작성자: 김진우",
            "Resources": {
                "Repository": {"Type": "AWS::ECR::Repository", "DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain", "Properties": {
                    "RepositoryName": "heapy-fastapi", "ImageTagMutability": "IMMUTABLE", "ImageScanningConfiguration": {"ScanOnPush": True}}},
                "DeployDocument": {"Type": "AWS::SSM::Document", "Properties": {"Name": "heapy-fastapi-dev-deploy", "DocumentType": "Command", "Content": command}},
                "GithubRole": {"Type": "AWS::IAM::Role", "Properties": {"RoleName": "heapy-fastapi-github-role", "MaxSessionDuration": 3600,
                    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
                        "Principal": {"Federated": f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"},
                        "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                            "token.actions.githubusercontent.com:sub": "repo:Heapy-AI@305710690/heapy-ai-health@1307957580:ref:refs/heads/dev"}}}]},
                    "Policies": [{"PolicyName": "fastapi-dev-deploy", "PolicyDocument": policy}]}},
                "InstancePull": {"Type": "AWS::IAM::Policy", "Properties": {"PolicyName": "heapy-fastapi-ecr-pull", "Roles": ["heapy-backend-dev-ec2-role"],
                    "PolicyDocument": {"Version": "2012-10-17", "Statement": [statement(["ecr:GetAuthorizationToken"], "*"), statement(pull, REPOSITORY)]}}}}}


if __name__ == "__main__":
    print(json.dumps(template(), ensure_ascii=False, indent=2))
