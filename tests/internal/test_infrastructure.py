"""배포 권한 범위 및 비밀 제외 검증. 작성자: 김진우."""
import unittest
from pathlib import Path
from scripts.deploy.render_infrastructure import template, INSTANCE, DOCUMENT, REPOSITORY


class InfrastructureTest(unittest.TestCase):
    def test_oidc_scoped_to_exact_repo_and_dev(self):
        role = template()['Resources']['GithubRole']['Properties']
        condition = role['AssumeRolePolicyDocument']['Statement'][0]['Condition']['StringEquals']
        self.assertEqual('repo:Heapy-AI@305710690/heapy-ai-health@1307957580:ref:refs/heads/dev', condition['token.actions.githubusercontent.com:sub'])
        statements = role['Policies'][0]['PolicyDocument']['Statement']
        ssm = next(item for item in statements if 'ssm:SendCommand' in item['Action'])
        self.assertEqual([INSTANCE, DOCUMENT], ssm['Resource'])
        for item in statements:
            self.assertFalse(any(action.startswith('iam:') for action in item['Action']))

    def test_fixed_document_only_accepts_digest(self):
        document = template()['Resources']['DeployDocument']['Properties']['Content']
        self.assertEqual(['ImageDigest'], list(document['parameters']))
        self.assertEqual('ENV_VAR', document['parameters']['ImageDigest']['interpolationType'])
        script = Path('scripts/deploy/deploy.sh').read_text(encoding='utf-8')
        self.assertNotIn('--privileged', script)
        self.assertNotIn('-p 8000', script)
        self.assertNotIn('docker logs', script)
        self.assertIn('--memory 1600m', script)


if __name__ == '__main__':
    unittest.main()
