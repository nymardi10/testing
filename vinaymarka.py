import boto3

ec2 = boto3.client('ec2')
instance_stop_waiter = ec2.get_waiter('instance_stopped')
snapshot_create_waiter = ec2.get_waiter('snapshot_completed')
volume_waiter = ec2.get_waiter('volume_available')


def stop_instance(id):
    response = ec2.stop_instances(InstanceIds=[id])
    return


def create_snapshots(i):
    id = i['instanceId']
    print('creating snapshots for instance {}'.format(id))
    response = ec2.create_snapshots(
        Description=f'{id} EBS Volume Snapshots',
        InstanceSpecification={
            'InstanceId': id,
            'ExcludeBootVolume': False,
        }
    )
    ids = []
    for j in range(0, len(response['Snapshots'])):
        ids.append(response['Snapshots'][j]['SnapshotId'])

    for df1 in i['volumes']:
        for df2 in response['Snapshots']:
            if df1['volumeId'] == df2['VolumeId']:
                df1.update({"snapshotId": df2['SnapshotId']})

    snapshot_create_waiter.wait(
        Filters=[
            {
                'Name': 'status',
                'Values': [
                    'completed',
                ]
            },
        ],
        SnapshotIds=ids,
        WaiterConfig={
            'Delay': 10,
            'MaxAttempts': 40
        }
    )
    return i


def create_volume(i):
    id = i['instanceId']
    print('creating volumes for instance {}'.format(id))
    volumeIDs = []
    for v in i['volumes']:
        response = ec2.create_volume(
            AvailabilityZone=v['zone'],
            Encrypted=True,
            KmsKeyId='',
            Iops=v['iops'],
            Size=v['size'],
            SnapshotId=v['snapshotId'],
            VolumeType=v['volumeType']
        )
        id = response['Attachments'][0]['VolumeId']
        volumeIDs.append(id)
        v.update({"newVolumeId": id})

    volume_waiter.wait(
        Filters=[
            {
                'Name': 'status',
                'Values': [
                    'available',
                ]
            },
        ],
        VolumeIds=volumeIDs,
        WaiterConfig={
            'Delay': 5,
            'MaxAttempts': 40
        }
    )

    return i


def detach_volumes(i):
    id = i['instanceId']
    volumes = i['volumes']
    print('detaching old volumes for instance {}'.format(id))
    for j in range(0, len(volumes)):
        ec2.detach_volume(
            Force=True,
            InstanceId=id,
            VolumeId=volumes[j]['volumeId']
        )
        volume_waiter.wait(
            Filters=[
                {
                    'Name': 'status',
                    'Values': [
                        'available',
                    ]
                },
            ],
            VolumeIds=volumes[j]['volumeId'],
            WaiterConfig={
                'Delay': 5,
                'MaxAttempts': 40
            }
        )
        # ec2.delete_volume(VolumeId=volumes[i])
    return


def attach_volumes(i):
    id = i['instanceId']
    volumes = i['volumes']
    print('attaching new volumes for instance {}'.format(id))
    for j in volumes:
        response = ec2.attach_volume(
            Device='string',
            InstanceId=id,
            VolumeId=j['newVolumeId']
        )
    return


def volume_process(i):
    snapshots = create_snapshots(i)
    volumeIds = create_volume(snapshots)
    detach_volumes(volumeIds)
    attach_volumes(volumeIds)

    return volumeIds


def main(List):
    for i in List:
        id = i['instanceId']
        stop_instance(id)
        instance_stop_waiter.wait(
            Filters=[
                {
                    'Name': 'instance-state-name',
                    'Values': [
                        'stopped',
                    ]
                },
            ],
            InstanceIds=[id],
            WaiterConfig={
                'Delay': 5,
                'MaxAttempts': 10
            }
        )
        response = volume_process(i)
        print('starting instance {}'.format(id))
        ec2.start_instances(InstanceIds=[id])

    return response


if __name__ == "__main__":
    l = []
    res = ec2.describe_volumes(
        Filters=[
            {
                'Name': 'encrypted',
                'Values': [
                    "false",
                ]
            },
        ]
    )
    volumes = res['Volumes']
    for i in range(0, len(volumes)):
        for j in range(0, len(volumes[i]['Attachments'])):
            List = {}
            List['zone'] = volumes[i]['AvailabilityZone']
            List['size'] = volumes[i]['Size']
            List['iops'] = volumes[i]['Iops']
            List['volumeType'] = volumes[i]['VolumeType']
            List['instanceId'] = volumes[i]['Attachments'][j]['InstanceId']
            List['volumeId'] = volumes[i]['Attachments'][j]['VolumeId']
            List['device'] = volumes[i]['Attachments'][j]['Device']
            l.append(List)

    # Get all unique values of key 'instanceId'.
    instances = list(set(i['instanceId'] for i in l))
    newList = []
    for m in instances:
        new = {}
        new['instanceId'] = m
        new['volumes'] = []
        for k in l:
            if k['instanceId'] == m:
                vol = {}
                vol['zone'] = k['zone']
                vol['size'] = k['size']
                vol['iops'] = k['iops']
                vol['volumeType'] = k['volumeType']
                vol['volumeId'] = k['volumeId']
                vol['device'] = k['device']
                new['volumes'].append(vol)
        newList.append(new)
    results = main(newList)
    
    