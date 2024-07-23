import os
import pandas as pd
from datetime import datetime, timedelta
import sys

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from utils.connection import AWSConnection
from settings.config import EBS_PRICING
from settings.models import AWSProfile
from utils.email_handler import email_handler
from utils.utils import load_service_data_v2, generate_report


class EBSReport:
    def __init__(self, account: AWSProfile, date: str):
        self.account = account
        self.date = date
        self.service_name = "ebs"
        self.data = load_service_data_v2(
            dir_path=os.path.join(account.accountID, date),
            file_name="volumes.json",
            root_element="Volumes",
            enabled_regions=account.aws_enabled_regions,
        )

    def get_volume_iops(self, volume_id, region) -> list | int:
        read_iops = self.get_iops_details(
            volume_id, metrics_name="VolumeReadOps", stats="Maximum", region=region
        )
        write_iops = self.get_iops_details(
            volume_id, metrics_name="VolumeWriteOps", stats="Maximum", region=region
        )
        iops = read_iops + write_iops
        return iops  # TODO: Get the read and write IOPS of same time and return the sum

    def get_iops_details(self, volume_id, metrics_name, stats, region) -> list | bool:
        try:
            cloudwatch_client = AWSConnection(
                service_name="cloudwatch", region=region, account=self.account
            ).client()
            response = cloudwatch_client.get_metric_statistics(
                Namespace="AWS/EBS",
                MetricName=metrics_name,
                Dimensions=[
                    {"Name": "VolumeId", "Value": volume_id},
                ],
                StartTime=datetime.now() - timedelta(days=14),
                EndTime=datetime.now(),
                Period=86400,
                Statistics=[stats],
            )
            if stats == "Maximum":
                datapoints_max = (
                    max([datapoint["Maximum"] for datapoint in response["Datapoints"]])
                    if response["Datapoints"]
                    else 0
                )
                return datapoints_max
            elif stats == "Sum":
                datapoints_sum = (
                    sum([datapoint["Sum"] for datapoint in response["Datapoints"]])
                    if response["Datapoints"]
                    else 0
                )
            return datapoints_sum
        except Exception as e:
            print(f"{e}")
            return 0

    @staticmethod
    def create_volume_df(volumes, recommendation_msg):
        data = [
            {
                "VolumeId": volume["VolumeId"],
                "Size": volume["Size"],
                "VolumeType": volume["VolumeType"],
                "Iops": volume["Iops"],
                "Throughput": volume.get("Throughput", 0),
                "State": volume["State"],
                "CreateTime": volume["CreateTime"],
                "AvailabilityZone": volume["AvailabilityZone"],
                "SnapshotId": volume["SnapshotId"],
                "SavingsPossible": volume["Savings"],
                "Region": volume.get("Region", ""),
                "Recommendation": volume.get("Recommendation", recommendation_msg),
            }
            for volume in volumes
        ]
        return pd.DataFrame(data)

    def calculate_savings(self, volumes: list):
        for volume in volumes:
            savings = 0
            if volume["VolumeType"] == "gp2":
                savings = volume["Size"] * EBS_PRICING[volume["Region"]]["gp2_perGB"]
            elif volume["VolumeType"] in ["io1", "io2"]:
                savings = volume["Size"] * EBS_PRICING[volume["Region"]]["io1_perGB"]
                savings += volume["Iops"] * EBS_PRICING[volume["Region"]]["io1_iops"]
            elif volume["VolumeType"] == "gp3":
                savings = volume["Size"] * EBS_PRICING[volume["Region"]]["gp3_perGB"]
                if volume["Iops"] > 3000:
                    savings += (volume["Iops"] - 3000) * EBS_PRICING[volume["Region"]][
                        "gp3_iops"
                    ]
                if volume["Throughput"] > 125:
                    savings += (volume["Throughput"] - 125) * EBS_PRICING[
                        volume["Region"]
                    ]["gp3_throughput"]
            volume["Savings"] = savings
        return volumes

    def send_report(self):
        volume_ids_from_instances = set()
        available_volumes = list()
        zero_iops_volume = list()
        gp2_volumes = list()
        io1_volumes = list()
        io2_volumes = list()

        instance_data = load_service_data_v2(
            dir_path=os.path.join(self.account.accountID, self.date),
            file_name="instances.json",
            root_element="Reservations",
            enabled_regions=self.account.aws_enabled_regions,
        )

        for iData in instance_data:
            for attachments in iData["Instances"][0]["BlockDeviceMappings"]:
                if attachments.get("Ebs"):
                    volume_ids_from_instances.add(attachments["Ebs"]["VolumeId"])

        for volume_data in self.data:

            if volume_data["State"] == "available":
                available_volumes.append(volume_data)
            elif (
                self.get_volume_iops(volume_data["VolumeId"], volume_data["Region"])
                == 0
            ):
                zero_iops_volume.append(volume_data)
            elif volume_data["VolumeType"] == "gp2":
                gp2_volumes.append(volume_data)
            elif volume_data["VolumeType"] == "io1":
                io1_volumes.append(volume_data)
            elif (
                volume_data["VolumeType"] == "io2"
                and self.get_volume_iops(volume_data["VolumeId"], volume_data["Region"])
                <= 2500
            ):
                io2_volumes.append(volume_data)

        available_volumes = self.calculate_savings(available_volumes)
        zero_iops_volume = self.calculate_savings(zero_iops_volume)

        for volume in io1_volumes:
            savings = volume["Size"] * (
                EBS_PRICING[volume["Region"]]["io1_perGB"]
                - EBS_PRICING[volume["Region"]]["io2_perGB"]
            )
            if self.get_volume_iops(volume["VolumeId"], volume["Region"]) <= 2500:
                savings = volume["Size"] * (
                    EBS_PRICING[volume["Region"]]["io1_perGB"]
                    - EBS_PRICING[volume["Region"]]["gp3_perGB"]
                ) + volume["Iops"] * (EBS_PRICING[volume["Region"]]["io1_iops"])
                volume["Recommendation"] = (
                    "Can be converted to gp3, because it have less than 2500 IOPS"
                )

            elif volume["Iops"] <= 32000:
                savings += (
                    volume["Iops"] * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - volume["Iops"]
                    * EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"]
                )
            elif volume["Iops"] in range(32001, 64001):
                savings += (
                    32000 * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - 32000 * EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"]
                )
                left_iops = volume["Iops"] - 32000
                savings += (
                    left_iops * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - left_iops
                    * EBS_PRICING[volume["Region"]]["io2_iops"]["32k_to_64k"]
                )
            elif volume["Iops"] > 64000:
                savings += (
                    32000 * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - 32000 * EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"]
                )
                savings += (
                    32000 * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - 32000 * EBS_PRICING[volume["Region"]]["io2_iops"]["32k_to_64k"]
                )
                left_iops = volume["Iops"] - 64000
                savings += (
                    left_iops * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - left_iops
                    * EBS_PRICING[volume["Region"]]["io2_iops"]["64k_greater"]
                )
            volume["Savings"] = savings

        for volume in io2_volumes:
            volume["Savings"] = volume["Size"] * (
                EBS_PRICING[volume["Region"]]["io2_perGB"]
                - EBS_PRICING[volume["Region"]]["gp3_perGB"]
            ) + volume["Iops"] * (EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"])

        for volume in gp2_volumes:
            savings = (
                volume["Size"] * EBS_PRICING[volume["Region"]]["gp2_perGB"]
                - volume["Size"] * EBS_PRICING[volume["Region"]]["gp3_perGB"]
            )
            if volume["Iops"] > 3000:
                savings -= volume["Iops"] * EBS_PRICING[volume["Region"]]["gp3_iops"]
            if volume.get("Throughput", 0) > 125:
                savings -= (
                    volume["Throughput"]
                    * EBS_PRICING[volume["Region"]]["gp3_throughput"]
                )
            volume["Savings"] = savings

        available_volumes_df = self.create_volume_df(
            available_volumes, "Can be removed because the volume is available"
        )
        zero_iops_volume_df = self.create_volume_df(
            zero_iops_volume,
            "Can be removed, because it have zero IOPS for last 14 days",
        )
        gp2_volumes_df = self.create_volume_df(
            gp2_volumes,
            "Can be converted to gp3, because gp3 is more cost-effective than gp2",
        )
        io1_volumes_df = self.create_volume_df(
            io1_volumes, "Can be converted to io2, io2 is more efficient than io1"
        )
        io2_volumes_df = self.create_volume_df(
            io2_volumes, "Can be converted to gp3, because it have less than 2500 IOPS"
        )

        unoptimized_volume_df = pd.concat(
            [
                available_volumes_df,
                gp2_volumes_df,
                io1_volumes_df,
                zero_iops_volume_df,
                io2_volumes_df,
            ]
        )
        report_file_path = generate_report(
            os.path.join(self.account.accountID, self.date),
            unoptimized_volume_df,
            f"ebs_report_{self.date}",
        )
        template = email_handler.get_template(self.service_name)
        context = {
            "accountID": self.account.accountID,
            "available_volumes_count": len(available_volumes),
            "zero_iops_volumes_count": len(zero_iops_volume),
            "gp2_volumes_count": len(gp2_volumes),
            "io1_volumes_count": len(io1_volumes),
            "io2_volumes_count": len(io2_volumes),
            "available_volumes_size": (
                round(available_volumes_df["Size"].sum(), 2)
                if not available_volumes_df.empty
                else 0
            ),
            "zero_iops_volumes_size": (
                round(zero_iops_volume_df["Size"].sum(), 2)
                if not zero_iops_volume_df.empty
                else 0
            ),
            "gp2_volumes_size": (
                round(gp2_volumes_df["Size"].sum(), 2)
                if not gp2_volumes_df.empty
                else 0
            ),
            "io1_volumes_size": (
                round(io1_volumes_df["Size"].sum(), 2)
                if not io1_volumes_df.empty
                else 0
            ),
            "io2_volumes_size": (
                round(io2_volumes_df["Size"].sum(), 2)
                if not io2_volumes_df.empty
                else 0
            ),
            "available_volumes_saving": (
                round(available_volumes_df["SavingsPossible"].sum(), 2)
                if not available_volumes_df.empty
                else 0
            ),
            "zero_iops_volumes_saving": (
                round(zero_iops_volume_df["SavingsPossible"].sum(), 2)
                if not zero_iops_volume_df.empty
                else 0
            ),
            "gp2_volumes_saving": (
                round(gp2_volumes_df["SavingsPossible"].sum(), 2)
                if not gp2_volumes_df.empty
                else 0
            ),
            "io1_volumes_saving": (
                round(io1_volumes_df["SavingsPossible"].sum(), 2)
                if not io1_volumes_df.empty
                else 0
            ),
            "io2_volumes_saving": (
                round(io2_volumes_df["SavingsPossible"].sum(), 2)
                if not io2_volumes_df.empty
                else 0
            ),
            "total_price_saved": (
                round(unoptimized_volume_df["SavingsPossible"].sum(), 2)
                if not unoptimized_volume_df.empty
                else 0
            ),
        }
        rendered_template = template.render(context)
        email_handler.send_mail(
            recipients=self.account.recipients,
            subject="EBS Optimizer Report",
            messages=[rendered_template],
            attachments=[report_file_path],
        )

    def get_report(self):
        volume_ids_from_instances = set()
        available_volumes = list()
        zero_iops_volume = list()
        gp2_volumes = list()
        io1_volumes = list()
        io2_volumes = list()

        instance_data = load_service_data_v2(
            dir_path=os.path.join(self.account.accountID, self.date),
            file_name="instances.json",
            root_element="Reservations",
            enabled_regions=self.account.aws_enabled_regions,
        )

        for iData in instance_data:
            for attachments in iData["Instances"][0]["BlockDeviceMappings"]:
                if attachments.get("Ebs"):
                    volume_ids_from_instances.add(attachments["Ebs"]["VolumeId"])

        for volume_data in self.data:

            if volume_data["State"] == "available":
                available_volumes.append(volume_data)
            elif (
                self.get_volume_iops(volume_data["VolumeId"], volume_data["Region"])
                == 0
            ):
                zero_iops_volume.append(volume_data)
            elif volume_data["VolumeType"] == "gp2":
                gp2_volumes.append(volume_data)
            elif volume_data["VolumeType"] == "io1":
                io1_volumes.append(volume_data)
            elif (
                volume_data["VolumeType"] == "io2"
                and self.get_volume_iops(volume_data["VolumeId"], volume_data["Region"])
                <= 2500
            ):
                io2_volumes.append(volume_data)

        available_volumes = self.calculate_savings(available_volumes)
        zero_iops_volume = self.calculate_savings(zero_iops_volume)

        for volume in io1_volumes:
            savings = volume["Size"] * (
                EBS_PRICING[volume["Region"]]["io1_perGB"]
                - EBS_PRICING[volume["Region"]]["io2_perGB"]
            )
            if self.get_volume_iops(volume["VolumeId"], volume["Region"]) <= 2500:
                savings = volume["Size"] * (
                    EBS_PRICING[volume["Region"]]["io1_perGB"]
                    - EBS_PRICING[volume["Region"]]["gp3_perGB"]
                ) + volume["Iops"] * (EBS_PRICING[volume["Region"]]["io1_iops"])
                volume["Recommendation"] = (
                    "Can be converted to gp3, because it have less than 2500 IOPS"
                )

            elif volume["Iops"] <= 32000:
                savings += (
                    volume["Iops"] * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - volume["Iops"]
                    * EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"]
                )
            elif volume["Iops"] in range(32001, 64001):
                savings += (
                    32000 * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - 32000 * EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"]
                )
                left_iops = volume["Iops"] - 32000
                savings += (
                    left_iops * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - left_iops
                    * EBS_PRICING[volume["Region"]]["io2_iops"]["32k_to_64k"]
                )
            elif volume["Iops"] > 64000:
                savings += (
                    32000 * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - 32000 * EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"]
                )
                savings += (
                    32000 * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - 32000 * EBS_PRICING[volume["Region"]]["io2_iops"]["32k_to_64k"]
                )
                left_iops = volume["Iops"] - 64000
                savings += (
                    left_iops * EBS_PRICING[volume["Region"]]["io1_iops"]
                    - left_iops
                    * EBS_PRICING[volume["Region"]]["io2_iops"]["64k_greater"]
                )
            volume["Savings"] = savings

        for volume in io2_volumes:
            volume["Savings"] = volume["Size"] * (
                EBS_PRICING[volume["Region"]]["io2_perGB"]
                - EBS_PRICING[volume["Region"]]["gp3_perGB"]
            ) + volume["Iops"] * (EBS_PRICING[volume["Region"]]["io2_iops"]["0_to_32k"])

        for volume in gp2_volumes:
            savings = (
                volume["Size"] * EBS_PRICING[volume["Region"]]["gp2_perGB"]
                - volume["Size"] * EBS_PRICING[volume["Region"]]["gp3_perGB"]
            )
            if volume["Iops"] > 3000:
                savings -= volume["Iops"] * EBS_PRICING[volume["Region"]]["gp3_iops"]
            if volume.get("Throughput", 0) > 125:
                savings -= (
                    volume["Throughput"]
                    * EBS_PRICING[volume["Region"]]["gp3_throughput"]
                )
            volume["Savings"] = savings

        available_volumes_df = self.create_volume_df(
            available_volumes, "Can be removed because the volume is available"
        )
        zero_iops_volume_df = self.create_volume_df(
            zero_iops_volume,
            "Can be removed, because it have zero IOPS for last 14 days",
        )
        gp2_volumes_df = self.create_volume_df(
            gp2_volumes,
            "Can be converted to gp3, because gp3 is more cost-effective than gp2",
        )
        io1_volumes_df = self.create_volume_df(
            io1_volumes, "Can be converted to io2, io2 is more efficient than io1"
        )
        io2_volumes_df = self.create_volume_df(
            io2_volumes, "Can be converted to gp3, because it have less than 2500 IOPS"
        )
        context = {
                "date": self.date,
                "report_data": {
                    "available_volumes": {
                        "data": available_volumes_df.to_dict(orient="records"),
                        "columns": available_volumes_df.columns.tolist(),
                        "message": "List of all available volumes across the organization.",
                        "summary": [],
                    },
                    "zero_iops_volume": {
                        "data": zero_iops_volume_df.to_dict(orient="records"),
                        "columns": zero_iops_volume_df.columns.tolist(),
                        "message": "List of all volumes across the organization that are unused from last 7 days.",
                        "summary": [],
                    },
                    "gp2_volumes": {
                        "data": gp2_volumes_df.to_dict(orient="records"),
                        "columns": gp2_volumes_df.columns.tolist(),
                        "message": "List of all gp2 volumes across the organization that can be converted to gp3.",
                        "summary": [],
                    },
                    "io1_volumes": {
                        "data": io1_volumes_df.to_dict(orient="records"),
                        "columns": io1_volumes_df.columns.tolist(),
                        "message": "List of all io1 volumes across the organization that can be converted to io2.",
                        "summary": [],
                    },
                    "io2_volumes": {
                        "data": io2_volumes_df.to_dict(orient="records"),
                        "columns": io2_volumes_df.columns.tolist(),
                        "message": "List of all io2 volumes across the organization that can be converted to gp3.",
                        "summary": [],
                    },
                    "table_names": ["available_volumes", "zero_iops_volume", "gp2_volumes", "io1_volumes", "io2_volumes"],
                },
                "title": "EBS Optimizer Report",
            }
        return context


if __name__ == "__main__":
    from dotenv import load_dotenv
    from settings.config import ACCOUNTS

    load_dotenv(".env", override=True)
    ebs = EBSReport(account=ACCOUNTS[0], date="2024-05-28")
    ebs.send_report()
