import boto3
import datetime

ec2_client = boto3.client('ec2')

instance_ids = ['instance-id-1', 'instance-id-2']  # List of instance IDs to create AMIs from
retention_days = 10  # Set your retention period in days
ami_creator_tag_key = 'CreatedByLambda'  # Tag key to identify AMIs created by this Lambda function

def get_instance_name(instance_id):
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    tags = response['Reservations'][0]['Instances'][0].get('Tags', [])
    
    for tag in tags:
        if tag['Key'] == 'Name':
            return tag['Value']
    return instance_id  # Fallback to instance ID if no name tag found

def create_ami(instance_id):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    instance_name = get_instance_name(instance_id)
    ami_name = f"AMI-{instance_name}-{current_time}"
    
    response = ec2_client.create_image(
        InstanceId=instance_id, 
        Name=ami_name,
        NoReboot=True
    )
    ami_id = response['ImageId']
    print(f"AMI Created: {ami_id} for Instance: {instance_name}")
    
    # Add a tag to the AMI to identify it was created by this Lambda
    ec2_client.create_tags(
        Resources=[ami_id],
        Tags=[{'Key': ami_creator_tag_key, 'Value': 'True'}]
    )

def delete_old_amis():
    # Calculate the cutoff date
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    
    # Describe all AMIs created by this account
    images = ec2_client.describe_images(Owners=['self'])['Images']
    
    for image in images:
        # Check for the 'CreatedByLambda' tag
        tags = image.get('Tags', [])
        is_created_by_lambda = False
        for tag in tags:
            if tag['Key'] == ami_creator_tag_key and tag['Value'] == 'True':
                is_created_by_lambda = True
                break
        
        # If the AMI was created by this Lambda function and is older than the retention period, delete it
        if is_created_by_lambda:
            creation_date = image['CreationDate']
            ami_creation_date = datetime.datetime.strptime(creation_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            
            if ami_creation_date < cutoff_date:
                ami_id = image['ImageId']
                print(f"Deleting AMI: {ami_id} created on {ami_creation_date}")
                
                # Deregister the AMI
                ec2_client.deregister_image(ImageId=ami_id)
                
                # Delete associated snapshots
                for block_device in image['BlockDeviceMappings']:
                    snapshot_id = block_device.get('Ebs', {}).get('SnapshotId')
                    if snapshot_id:
                        try:
                            print(f"Deleting snapshot: {snapshot_id}")
                            ec2_client.delete_snapshot(SnapshotId=snapshot_id)
                        except Exception as e:
                            print(f"Error deleting snapshot {snapshot_id}: {e}")

def lambda_handler(event, context):
    # Create AMIs for specified instances
    for instance_id in instance_ids:
        try:
            create_ami(instance_id)
        except Exception as e:
            print(f"Error creating AMI for instance {instance_id}: {e}")
    
    # Delete old AMIs beyond the retention period
    delete_old_amis()