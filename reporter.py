from settings.models import AWSProfile
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


class ReportHandler:
    def __init__(self, service_name: str, account: AWSProfile, date: str, env=None):
        self.service_name = service_name
        self.account = account
        self.date = date
        self.env = env

    def send_report(self):
        reports = [
            EBSReport,
            AuroraReport,
            AutoTagToInstanceReports,
            COReports,
            InstanceReport,
            DynamoDbReport,
            EKSReports,
            ElasticIpReport,
            ELBReports,
            InstanceTagVolumeReports,
            IO1IO2Report,
            S3Reports,
            UCReports,
            VPCEndpointReport,
            VPNReport,
        ]
        for report in reports:
            try:
                reporter = report()
                reporter.send_report(
                    self.service_name, self.account, self.date, self.env
                )
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    from settings.config import ACCOUNTS

    ro = ReportHandler(service_name="ebs", account=ACCOUNTS[0], date="2024-07-11")
    ro.send_report()
