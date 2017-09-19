# Upside Travel, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import boto3
import clamav
import copy
import json
import metrics
import urllib
from common import *
from datetime import datetime

ENV = os.getenv("ENV", "")


def event_object(event):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.unquote_plus(event['Records'][0]['s3']['object']['key'].encode('utf8'))
    if (not bucket) or (not key):
        print("Unable to retrieve object from event.\n%s" % event)
        raise Exception("Unable to retrieve object from event.")
    return s3.Object(bucket, key)


def download_s3_object(s3_object, local_prefix):
    local_path = "%s/%s/%s" % (local_prefix, s3_object.bucket_name, s3_object.key)
    create_dir(os.path.dirname(local_path))
    s3_object.download_file(local_path)
    return local_path


def set_av_metadata(s3_object, result):
    content_type = s3_object.content_type
    metadata = s3_object.metadata
    metadata[AV_STATUS_METADATA] = result
    metadata[AV_TIMESTAMP_METADATA] = datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S UTC")
    s3_object.copy(
        {
            'Bucket': s3_object.bucket_name,
            'Key': s3_object.key
        },
        ExtraArgs={
            "ContentType": content_type,
            "Metadata": metadata,
            "MetadataDirective": "REPLACE"
        }
    )


def set_av_tags(s3_object, result):
    curr_tags = s3_client.get_object_tagging(Bucket=s3_object.bucket_name, Key=s3_object.key)["TagSet"]
    new_tags = copy.copy(curr_tags)
    for tag in curr_tags:
        if tag["Key"] == AV_STATUS_METADATA:
            new_tags.remove(tag)
            break
    new_tags.append({"Key": AV_STATUS_METADATA, "Value": result})
    new_tags.append({"Key": AV_TIMESTAMP_METADATA, "Value": datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S UTC")})
    s3_client.put_object_tagging(
        Bucket=s3_object.bucket_name,
        Key=s3_object.key,
        Tagging={"TagSet": new_tags}
    )


def sns_scan_results(s3_object, result):
    if AV_STATUS_SNS_ARN is None:
        return
    message = {
        "bucket": s3_object.bucket_name,
        "key": s3_object.key,
        AV_STATUS_METADATA: result,
        AV_TIMESTAMP_METADATA: datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S UTC")
    }
    sns_client = boto3.client("sns")
    sns_client.publish(
        TargetArn=AV_STATUS_SNS_ARN,
        Message=json.dumps({'default': json.dumps(message)}),
        MessageStructure="json"
    )


def lambda_handler(event, context):
    start_time = datetime.utcnow()
    print("Script starting at %s\n" %
          (start_time.strftime("%Y/%m/%d %H:%M:%S UTC")))
    s3_object = event_object(event)
    file_path = download_s3_object(s3_object, "/tmp")
    clamav.update_defs_from_s3(AV_DEFINITION_S3_BUCKET, AV_DEFINITION_S3_PREFIX)
    scan_result = clamav.scan_file(file_path)
    print("Scan of s3://%s resulted in %s\n" % (os.path.join(s3_object.bucket_name, s3_object.key), scan_result))
    if "AV_UPDATE_METADATA" in os.environ:
        set_av_metadata(s3_object, scan_result)
    set_av_tags(s3_object, scan_result)
    sns_scan_results(s3_object, scan_result)
    metrics.send(env=ENV, bucket=s3_object.bucket_name, key=s3_object.key, status=scan_result)
    # Delete downloaded file to free up room on re-usable lambda function container
    try:
        os.remove(file_path)
    except OSError:
        pass
    print("Script finished at %s\n" %
          datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S UTC"))