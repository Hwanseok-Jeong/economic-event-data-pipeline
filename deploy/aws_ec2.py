"""Account-free template generation and Free-plan-only one-off EC2 deployment."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent


def template():
    bootstrap=(HERE/'bootstrap.sh').read_text(encoding='utf-8')
    verify=(HERE/'verify_server.sh').read_text(encoding='utf-8')
    user_data={'Fn::Join':['',[
        '#!/bin/bash\nset -euo pipefail\nSOURCE_REF=',{'Ref':'RepositoryRef'},
        '\nSTOP_AFTER_MINUTES=',{'Ref':'StopAfterMinutes'},
        '\nexport SOURCE_REF STOP_AFTER_MINUTES\n',
        "cat > /opt/verify-economic-events.sh <<'VERIFY_SCRIPT'\n",verify,
        '\nVERIFY_SCRIPT\n',bootstrap]]}
    return {
        'AWSTemplateFormatVersion':'2010-09-09',
        'Description':'Temporary single-host Docker/MySQL/Streamlit validation; no credentials in template',
        'Parameters':{
            'ImageId':{'Type':'AWS::EC2::Image::Id'},
            'VpcId':{'Type':'AWS::EC2::VPC::Id'},
            'SubnetId':{'Type':'AWS::EC2::Subnet::Id'},
            'KeyName':{'Type':'AWS::EC2::KeyPair::KeyName'},
            'SshCidr':{'Type':'String'},
            'InstanceType':{'Type':'String','AllowedValues':['t3.small','t3.medium'],'Default':'t3.small'},
            'RepositoryRef':{'Type':'String','AllowedPattern':'[a-f0-9]{40}'},
            'StopAfterMinutes':{'Type':'Number','MinValue':30,'MaxValue':180,'Default':120}},
        'Resources':{
            'SshOnly':{'Type':'AWS::EC2::SecurityGroup','Properties':{
                'GroupDescription':'SSH tunnel from a single client address; dashboard and MySQL stay private',
                'VpcId':{'Ref':'VpcId'},
                'SecurityGroupIngress':[{'IpProtocol':'tcp','FromPort':22,'ToPort':22,'CidrIp':{'Ref':'SshCidr'}}]}},
            'Host':{'Type':'AWS::EC2::Instance','Properties':{
                'ImageId':{'Ref':'ImageId'},'InstanceType':{'Ref':'InstanceType'},'KeyName':{'Ref':'KeyName'},
                'MetadataOptions':{'HttpTokens':'required'},
                'InstanceInitiatedShutdownBehavior':'stop',
                'NetworkInterfaces':[{'DeviceIndex':'0','AssociatePublicIpAddress':True,
                    'SubnetId':{'Ref':'SubnetId'},'GroupSet':[{'Ref':'SshOnly'}]}],
                'BlockDeviceMappings':[{'DeviceName':'/dev/sda1','Ebs':{
                    'VolumeSize':20,'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':True}}],
                'UserData':{'Fn::Base64':user_data},
                'Tags':[{'Key':'Name','Value':'economic-events-validation'}]}}},
        'Outputs':{'InstanceId':{'Value':{'Ref':'Host'}},
                   'PublicIp':{'Value':{'Fn::GetAtt':['Host','PublicIp']}}}}


def cli(config,*arguments):
    portable=ROOT/'.cloud-tools/aws-cli/Amazon/AWSCLIV2/aws.exe'
    executable=shutil.which('aws') or (str(portable) if portable.is_file() else None)
    if not executable:
        raise RuntimeError('Install AWS CLI v2 and sign in with aws login')
    env=os.environ.copy()
    auth=ROOT/'outputs/aws/auth'
    if (auth/'config').is_file():
        env['AWS_CONFIG_FILE']=str(auth/'config')
        env['AWS_SHARED_CREDENTIALS_FILE']=str(auth/'credentials')
        env['AWS_LOGIN_CACHE_DIRECTORY']=str(auth/'login-cache')
    result=subprocess.run([executable,*arguments,'--profile',config['profile'],
                           '--region',config['region'],'--output','json','--no-cli-pager'],
                          env=env,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    if arguments[:2]==('cloudformation','deploy'):
        return {}  # The high-level deploy command emits human-readable progress.
    return json.loads(result.stdout) if result.stdout.strip() else {}


def parameters(config):
    mapping={'image_id':'ImageId','vpc_id':'VpcId','subnet_id':'SubnetId','key_name':'KeyName',
             'ssh_cidr':'SshCidr','instance_type':'InstanceType','repository_ref':'RepositoryRef',
             'stop_after_minutes':'StopAfterMinutes'}
    if any(not config.get(key) for key in mapping):
        raise ValueError('Fill all resource settings in aws-config.local.json; credentials/email are not settings')
    network=ipaddress.ip_network(config['ssh_cidr'],strict=True)
    if network.version!=4 or network.prefixlen!=32:
        raise ValueError('SSH must be restricted to one IPv4 address (/32)')
    if not re.fullmatch('[a-f0-9]{40}',config['repository_ref']):
        raise ValueError('Pin repository_ref to a full Git commit hash')
    if config['instance_type'] not in ['t3.small','t3.medium'] or not 30<=int(config['stop_after_minutes'])<=180:
        raise ValueError('Use the bounded validation instance type and runtime')
    return [f'{value}={config[key]}' for key,value in mapping.items()]


def require_free_plan(plan):
    credits=plan.get('accountPlanRemainingCredits',{}).get('amount',0)
    if plan.get('accountPlanType')!='FREE' or plan.get('accountPlanStatus')!='ACTIVE' or credits<=0:
        raise ValueError('Deployment requires an active Free plan with remaining credits; no automatic paid upgrade')
    return credits


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['template','preflight','deploy','status'])
    parser.add_argument('--config',default=str(HERE/'aws-config.local.json'))
    args=parser.parse_args()
    out=ROOT/'outputs/aws'
    out.mkdir(parents=True,exist_ok=True)
    path=out/'cloudformation.json'
    path.write_text(json.dumps(template(),indent=2)+'\n',encoding='utf-8')
    if args.command=='template':
        print('Generated account-free template: outputs/aws/cloudformation.json')
        return
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    if args.command in ['preflight','deploy']:
        cli(config,'sts','get-caller-identity')  # Authenticate without printing account identity.
        plan=cli(config,'freetier','get-account-plan-state')
        credits=require_free_plan(plan)
        print(json.dumps({'authenticated':True,'plan':'FREE','status':'ACTIVE','remaining_credits_usd':credits}))
    if args.command=='deploy':
        values=parameters(config)
        # Validate the template with AWS before resource creation.
        cli(config,'cloudformation','validate-template','--template-body','file://'+path.as_posix())
        cli(config,'cloudformation','deploy','--template-file',str(path),'--stack-name',config['stack_name'],
            '--parameter-overrides',*values,'--no-fail-on-empty-changeset')
    if args.command in ['status','deploy']:
        stack=cli(config,'cloudformation','describe-stacks','--stack-name',config['stack_name'])
        (out/'stack-state.json').write_text(json.dumps(stack,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'stack_status':stack['Stacks'][0]['StackStatus'],
                          'resource_details':'outputs/aws/stack-state.json',
                          'note':'Stack creation is not proof that application verification passed'}))


if __name__=='__main__':
    main()
