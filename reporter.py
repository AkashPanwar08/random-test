from dotenv import load_dotenv
from settings.config import ACCOUNTS, REGIONS
from datetime import datetime


from reports.generators.ebs import EBSReport
from reports.generators.aurora import AuroraReport
from reports.generators.autoscaling_tag_to_instance import AutoTagToInstanceReports
from reports.generators.compute_optimizer import COReports
from reports.generators.ec2_instance import InstanceReport
from reports.generators.dynamodb import DynamoDbReport
from reports.generators.eks import EKSReports
from reports.generators.elastic_ip import ElasticIpReport
from reports.generators.elb import ELBReports
from reports.generators.instances_tag_volume import InstanceTagVolumeReports
from reports.generators.io1_io2 import IO1IO2Report
from reports.generators.s3_bucket import S3Reports
from reports.generators.uncompressed_cloudfront import UCReports
from reports.generators.vpc_endpoints import VPCEndpointReport
from reports.generators.vpn import VPNReport
from reports.generators.snapshot import SnapshotReport

load_dotenv(".env", override=True)


if __name__ == "__main__":
    print("Welcome to AWS Bill Buster")
    DATE = datetime.now().strftime("%Y-%m-%d")
    ENV = "prod"
    for account in ACCOUNTS:
        for serviceName in account.enabled_reports:
            for region in account.aws_enabled_regions:
                if region in REGIONS:
                    try:
                        ro = AuroraReport(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = AutoTagToInstanceReports(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = COReports(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = DynamoDbReport(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ebs = EBSReport(account=ACCOUNTS[0], date=DATE)
                        ebs.send_report()

                        ro = InstanceReport(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = EKSReports(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = ELBReports(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = InstanceTagVolumeReports(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ebs = IO1IO2Report(accounts=ACCOUNTS, date=DATE)
                        ebs.send_report()

                        ro = S3Reports(account=ACCOUNTS[0], date=DATE)
                        ro.send_report()

                        ro = SnapshotReport(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = UCReports(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = VPCEndpointReport(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                        ro = ElasticIpReport(accounts=ACCOUNTS, date=DATE)
                        ro.send_report()

                    except Exception as e:
                        print(f"Error in {serviceName} report: {e}")
