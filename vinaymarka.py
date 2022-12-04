import boto3
import time
import sys
import random

EC2_RESOURCE = boto3.resource('ec2',region_name='us-east-1')
EC2_CLIENT = boto3.client('ec2',region_name='us-east-1')
INSTANCE_ID = input('Enter Instance Id - Format i-..... :')

def find_volumes(instance):
    ec2 = boto3.resource('ec2', region_name="us-east-1")
    response_instance = ec2.Instance(instance)
    volumes = response_instance.volumes.all()
    response = []
    for item in volumes:
        response.append(
            {"volume": item.id, "type": item.volume_type, "az": response_instance.placement['AvailabilityZone'], 'device': item.attachments[0]['Device']})
    return response

def stop_instances(instance_id):
    state = EC2_CLIENT.stop_instances(
            InstanceIds = [instance_id]
    )
    if not state['StoppingInstances'][0]['CurrentState']['Code'] in [64,80]:
       print('Not Stopped')
       sys.exit(1)
    response = find_volumes(instance_id)
    return response

def create_image(instance_id):
    instance = EC2_RESOURCE.Instance(instance_id)
    generate_keys = random.randint(1, 100)
    image = instance.create_image(
        Name='AMI-image-created-by-automation' + '-' + instance_id +'-'+ str(generate_keys),
        Description='This is the AMI for:' + instance_id +'-'+ str(generate_keys),
        NoReboot=True
    )
    print(f'AMI creation started: {image.id}')
    print('This process might take a while depending on the size of the volumes')

    image.wait_until_exists(
        Filters=[
            {
                'Name': 'state',
                'Values': ['available']
            }
        ]
    )
    print(f'AMI {image.id} successfully created')

def create_snapshot(volume_ids, instance_id):
    response = []
    for item in volume_ids:
        snapshot = EC2_RESOURCE.create_snapshot(
            VolumeId=item['volume'],
            TagSpecifications=[
                {
                    'ResourceType': 'snapshot',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': 'Snapshot created for1: ' + item['volume'] + '-' + instance_id
                        },
                    ]
                },
            ]
        )
        print(f'Creating Snapshot {snapshot.id} for volume {item}')
        response.append({"snapshot": snapshot.id, "volume": item['volume'], "type": item['type'], "az": item['az'], 'device': item['device']})
        time.sleep(60)
    return response

def create_volume(snapshots, instance_id):
    response = []
    for item in snapshots:
        print('Creating Volume(s)')
        volume = EC2_CLIENT.create_volume(
            AvailabilityZone=item['az'],
            Encrypted=True,
            KmsKeyId= 'kms_key'
            SnapshotId=item['snapshot'],
            VolumeType=item['type'],
        )
        
        key = {'volume': volume['VolumeId'], "type": item['type'], 'device': item['device']}
        print(key)
        response.append(key)
    time.sleep(20)
    return response

def detach_volume(instance_id, volume_ids):
    # EC2_RESOURCE.Instance(INSTANCE_ID).stop()
    # time.sleep(15)
    for item in volume_ids:
        print("Detaching unencrypted Volume(s)")
        response = EC2_CLIENT.detach_volume(
            Force=False,
            InstanceId=instance_id,
            VolumeId= item['volume']
            # DryRun=True
        )
        time.sleep(20)

def attach_volume(instance_id, new_volume_ids):
    for item in new_volume_ids:
        print("Attaching new encrypted Volume")
        response = EC2_CLIENT.attach_volume(
            Device = item['device'],
            InstanceId=instance_id,
            VolumeId= item['volume']
            # DryRun=True
        )
        time.sleep(20)
    EC2_RESOURCE.Instance(instance_id).start()

volume_ids = stop_instances(INSTANCE_ID)
create_image(INSTANCE_ID)
snapshots = create_snapshot(volume_ids,INSTANCE_ID)
new_volume_ids = create_volume(snapshots,INSTANCE_ID)
detach_volume(INSTANCE_ID, volume_ids)
attach_volume(INSTANCE_ID, new_volume_ids)
