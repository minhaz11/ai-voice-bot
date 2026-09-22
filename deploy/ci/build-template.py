"""Regenerate the CloudFormation CI stack after changing deploy-release.sh."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
sub = {'Fn::Sub': 'arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:instance/${InstanceId}'}
template = {
    'AWSTemplateFormatVersion': '2010-09-09',
    'Description': 'GitHub OIDC and restricted SSM deployment for Jannet',
    'Parameters': {'InstanceId': {'Type': 'AWS::EC2::Instance::Id'},
                   'GitHubSubject': {'Type': 'String'}},
    'Resources': {
        'GitHubProvider': {'Type': 'AWS::IAM::OIDCProvider', 'Properties': {
            'Url': 'https://token.actions.githubusercontent.com', 'ClientIdList': ['sts.amazonaws.com']}},
        'DeployDocument': {'Type': 'AWS::SSM::Document', 'Properties': {
            'DocumentType': 'Command', 'UpdateMethod': 'NewVersion',
            'Content': {'schemaVersion': '2.2', 'description': 'Deploy a main-branch Jannet commit with health check and rollback',
                'parameters': {'Commit': {'type': 'String', 'allowedPattern': '^[0-9a-f]{40}$', 'interpolationType': 'ENV_VAR'}},
                'mainSteps': [{'action': 'aws:runShellScript', 'name': 'deploy', 'inputs': {
                    'timeoutSeconds': '1200',
                    'runCommand': ["bash <<'JANNET_DEPLOY_SCRIPT'\n" + (root/'deploy-release.sh').read_text() + '\nJANNET_DEPLOY_SCRIPT']}}]}}},
        'DeployRole': {'Type': 'AWS::IAM::Role', 'Properties': {
            'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{
                'Effect': 'Allow', 'Principal': {'Federated': {'Ref': 'GitHubProvider'}},
                'Action': 'sts:AssumeRoleWithWebIdentity', 'Condition': {'StringEquals': {
                    'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
                    'token.actions.githubusercontent.com:sub': {'Ref': 'GitHubSubject'}}}}]},
            'Policies': [{'PolicyName': 'DeployOnlyJannet', 'PolicyDocument': {
                'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': 'ssm:SendCommand', 'Resource': [sub,
                     {'Fn::Sub': 'arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:document/${DeployDocument}'}]},
                    # GetCommandInvocation does not support resource-level permissions.
                    {'Effect': 'Allow', 'Action': 'ssm:GetCommandInvocation', 'Resource': '*'}]}}]}}},
    'Outputs': {'RoleArn': {'Value': {'Fn::GetAtt': ['DeployRole', 'Arn']}},
                'DocumentName': {'Value': {'Ref': 'DeployDocument'}}}}
(root/'template.json').write_text(json.dumps(template, indent=2)+'\n')
