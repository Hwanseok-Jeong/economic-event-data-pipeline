"""Deployment boundary checks without AWS credentials or resource creation."""
import json
import unittest
from deploy.aws_ec2 import parameters, require_free_plan, template


class DeploymentTests(unittest.TestCase):
    def test_free_plan_gate(self):
        plan={'accountPlanType':'FREE','accountPlanStatus':'ACTIVE',
              'accountPlanRemainingCredits':{'amount':100}}
        self.assertEqual(require_free_plan(plan),100)
        for change in [{'accountPlanType':'PAID'},{'accountPlanStatus':'EXPIRED'},
                       {'accountPlanRemainingCredits':{'amount':0}}]:
            with self.assertRaises(ValueError):
                require_free_plan(dict(plan,**change))

    def test_remote_exposure_and_runtime(self):
        result=template()
        json.dumps(result)  # All intrinsic functions are JSON-serializable.
        resources=result['Resources']
        ingress=resources['SshOnly']['Properties']['SecurityGroupIngress']
        self.assertEqual([(r['FromPort'],r['ToPort']) for r in ingress],[(22,22)])
        host=resources['Host']['Properties']
        self.assertEqual(host['MetadataOptions']['HttpTokens'],'required')
        self.assertTrue(host['BlockDeviceMappings'][0]['Ebs']['Encrypted'])
        self.assertEqual(host['InstanceInitiatedShutdownBehavior'],'stop')
        self.assertNotIn('IamInstanceProfile',host)

    def test_refuses_unbounded_client_access(self):
        config={k:'example' for k in ['image_id','vpc_id','subnet_id','key_name']}
        config.update(ssh_cidr='0.0.0.0/0',instance_type='t3.small',repository_ref='a'*40,stop_after_minutes=120)
        with self.assertRaises(ValueError):
            parameters(config)
        config['ssh_cidr']='192.0.2.1/32'
        self.assertEqual(len(parameters(config)),8)
        config['stop_after_minutes']=999
        with self.assertRaises(ValueError):
            parameters(config)
