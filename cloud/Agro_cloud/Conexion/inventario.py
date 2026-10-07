#inventario de solo lectura: lista lo que existe en la cuenta, no borra nada
import boto3,os,sys
os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE",os.path.join(os.path.dirname(os.path.abspath(__file__)),"credenciales.txt"))
s=boto3.Session(region_name="us-east-1")
def sec(t,f):
    try: r=f(); print(f"{t}: {r if r else '-'}")
    except Exception as e: print(f"{t}: ERROR {type(e).__name__} {str(e)[:120]}")
print("cuenta", s.client("sts").get_caller_identity()["Account"])
sec("alb",lambda:[(x["LoadBalancerName"],x["State"]["Code"]) for x in s.client("elbv2").describe_load_balancers()["LoadBalancers"]])
sec("target groups",lambda:[x["TargetGroupName"] for x in s.client("elbv2").describe_target_groups()["TargetGroups"]])
ecs=s.client("ecs")
def ecsf():
    out=[]
    for c in ecs.list_clusters()["clusterArns"]:
        sv=ecs.list_services(cluster=c)["serviceArns"]; tk=ecs.list_tasks(cluster=c)["taskArns"]
        out.append((c.split("/")[-1],len(sv),len(tk)))
    return out
sec("ecs clusters (servicios,tareas)",ecsf)
sec("task definitions activas",lambda:ecs.list_task_definitions(status="ACTIVE")["taskDefinitionArns"])
sec("ecr",lambda:[x["repositoryName"] for x in s.client("ecr").describe_repositories()["repositories"]])
sec("s3",lambda:[x["Name"] for x in s.client("s3").list_buckets()["Buckets"]])
sec("sqs",lambda:s.client("sqs").list_queues().get("QueueUrls"))
sec("lambda",lambda:[x["FunctionName"] for x in s.client("lambda").list_functions()["Functions"]])
sec("lambda mappings",lambda:[x["UUID"] for x in s.client("lambda").list_event_source_mappings()["EventSourceMappings"]])
sec("cognito",lambda:[x["Name"] for x in s.client("cognito-idp").list_user_pools(MaxResults=60)["UserPools"]])
sec("dynamodb",lambda:s.client("dynamodb").list_tables()["TableNames"])
sec("log groups",lambda:[x["logGroupName"] for x in s.client("logs").describe_log_groups()["logGroups"]])
sec("scheduler",lambda:[x["Name"] for x in s.client("scheduler").list_schedules()["Schedules"]])
aas=s.client("application-autoscaling")
sec("autoscaling ecs",lambda:[x["ResourceId"] for x in aas.describe_scalable_targets(ServiceNamespace="ecs")["ScalableTargets"]])
ec2=s.client("ec2")
sec("vpcs",lambda:[(x["VpcId"],x.get("IsDefault")) for x in ec2.describe_vpcs()["Vpcs"]])
sec("sg no default",lambda:[(x["GroupName"],x["GroupId"]) for x in ec2.describe_security_groups()["SecurityGroups"] if x["GroupName"]!="default"])
sec("eni",lambda:[(x["NetworkInterfaceId"],x["InterfaceType"],x.get("Description","")[:40]) for x in ec2.describe_network_interfaces()["NetworkInterfaces"]])
sec("elastic ip",lambda:[x["PublicIp"] for x in ec2.describe_addresses()["Addresses"]])
sec("ec2 instancias",lambda:[(i["InstanceId"],i["State"]["Name"]) for r in ec2.describe_instances()["Reservations"] for i in r["Instances"]])
sec("nat",lambda:[x["NatGatewayId"] for x in ec2.describe_nat_gateways()["NatGateways"] if x["State"]!="deleted"])
sec("codebuild",lambda:s.client("codebuild").list_projects()["projects"])
sec("etiquetados",lambda:[x["ResourceARN"] for x in s.client("resourcegroupstaggingapi").get_resources()["ResourceTagMappingList"]])
