from dotenv import load_dotenv
from settings.config import ACCOUNTS, REGIONS
from datetime import datetime

from utils.email_handler import email_handler

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
    reports = []
    for account in ACCOUNTS:
        try:
            ro = AuroraReport(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("Aurora report generated")
        except Exception as e:
            print(f"Error in generating Aurora report: {e}")

        try:
            ro = AutoTagToInstanceReports(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("Auto Tag report generated")
        except Exception as e:
            print(f"Error in generating AutoTagToInstance report: {e}")

        try:
            ro = COReports(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())

            print("CO report generated")
        except Exception as e:
            print(f"Error in generating CO report: {e}")

        try:
            ro = DynamoDbReport(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())

            print("DynamoDB report generated")
        except Exception as e:
            print(f"Error in generating DynamoDB report: {e}")

        # try:
        #     ebs = EBSReport(account=account, date=DATE)
        #     reports.append(ebs.get_report())
        # except Exception as e:
        #     print(f"Error in generating EBS report: {e}")

        try:
            ro = InstanceReport(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())

            print("Instance report generated")
        except Exception as e:
            print(f"Error in generating Instance report: {e}")

        try:
            ro = EKSReports(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())

            print("EKS report generated")
        except Exception as e:
            print(f"Error in generating EKS report: {e}")

        try:
            ro = ELBReports(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("ELB report generated")
        except Exception as e:
            print(f"Error in generating ELB report: {e}")

        try:
            ro = InstanceTagVolumeReports(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("Instance report generated")
        except Exception as e:
            print(f"Error in generating InstanceTagVolume report: {e}")

        try:
            io1op2 = IO1IO2Report(accounts=ACCOUNTS, date=DATE)
            reports.append(io1op2.get_report())
            print("IO1IO2 report generated")
        except Exception as e:
            print(f"Error in generating IO1IO2 report: {e}")

        try:
            ro = S3Reports(account=account, date=DATE)
            reports.append(ro.get_report())
            print("S3 report generated")
        except Exception as e:
            print(f"Error in generating S3 report: {e}")

        try:
            ro = SnapshotReport(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("Snapshot report generated")
        except Exception as e:
            print(f"Error in generating Snapshot report: {e}")

        try:
            ro = UCReports(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("UC report generated")
        except Exception as e:
            print(f"Error in generating UC report: {e}")

        try:
            ro = VPCEndpointReport(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
        except Exception as e:
            print(f"Error in generating VPCEndpoint report: {e}")

        try:
            ro = ElasticIpReport(accounts=ACCOUNTS, date=DATE)
            reports.append(ro.get_report())
            print("Elastic IP report generated")
        except Exception as e:
            print(f"Error in generating ElasticIp report: {e}")
        template = email_handler.get_template("reporter")
        context = {"reports": reports}
        rendered_template = template.render(context)
        email_handler.send_mail(
            recipients=account.recipients,
            subject="AWS Cost Optimizer Report",
            messages=[rendered_template],
            attachments=[],
        )
