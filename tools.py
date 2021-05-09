import os
import io
import json
from pprint import pprint as pp
from datetime import datetime, timezone
import codecs

import boto3
import botocore
from botocore.exceptions import ClientError
import requests
import urllib.error


s3 = boto3.client("s3")
lamd = boto3.client("lambda")
cloudwatch = boto3.client("logs")


def dictBytes2B64(d):
    new_d = {}
    for key, value in d.items():
        if isinstance(value, bytes) or isinstance(value, bytearray):
            new_d[key + "_b64"] = codecs.encode(value, "base64").decode()
        else:
            new_d[key] = value
    return new_d


def dictB642Bytes(d):
    new_d = {}
    for key, value in d.items():
        if key.endswith("_b64"):
            new_d[key[:-4]] = codecs.decode(value.encode(), "base64")
        else:
            new_d[key] = value
    return new_d


def toJSON(d, filename="output.json"):
    if isinstance(filename, int):
        filename = "output_{}.json".format(filename)

    with open(filename, "w") as f:
        json.dump(d, f, indent=2)



def shard_list(items, shard_size):
    items_list = []
    for i in range(0, len(items), shard_size):
        items_list.append(items[i: i+shard_size])
    return items_list


def getJSONFroms3(bucket, key):
    text = getTextFroms3(bucket, key)
    if text is None:
        return None
    d = json.loads(text)
    return d


def getListFromS3(bucket, key):
    raw_text = getTextFroms3(bucket, key)
    if raw_text is None:
        return None
    return raw_text.splitlines()

def saveListToS3(input_list, bucket, key):
    raw_text = "\n".join(input_list)
    saveTextToS3(raw_text, bucket, key)


def getJSON(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def getTag(context, key):

    if not hasattr(context, "invoked_function_arn") or context.invoked_function_arn is None:
        return None

    response = lamd.list_tags(Resource=context.invoked_function_arn)

    if response is None or not isinstance(response, dict) or "Tags" not in response:
        return None

    tags = response["Tags"]
    try:
        return tags[key]
    except KeyError:
        return None


def saveTag(context, key, tag):

    if not hasattr(context, "invoked_function_arn") or context.invoked_function_arn is None:
        print("Unable to find ARN of function.")
        pp(context)
        return

    lamd.tag_resource(Resource=context.invoked_function_arn, Tags={str(key): str(tag)})


def getTextFroms3(bucket, key):
    bytes_buffer = io.BytesIO()
    try:
        s3.download_fileobj(Bucket=bucket, Key=key, Fileobj=bytes_buffer)
    except ClientError as e:
        print("Could not get {} from s3.".format(key))
        return None
    byte_value = bytes_buffer.getvalue()
    str_value = byte_value.decode()
    return str_value


def saveJSONtos3(d, bucket, key, indent=None):
    saveTextToS3(json.dumps(d, indent=indent, ensure_ascii=False), bucket, key)


def saveTextToS3(text, bucket, s3_key):
    s3.put_object(Body=text,  Bucket=bucket, Key=s3_key)


def saveImageToS3(image, bucket, s3_key):
    # Get extension name
    obj_name, extension = os.path.splitext(s3_key)

    # Get Pillow image type from the extension
    img_format = (extension[1:] if extension.startswith(".") else extension).upper()
    img_format = ("JPEG" if img_format == "JPG" else img_format)

    image_bytes = io.BytesIO()
    if img_format == "JPEG":
        image.save(image_bytes, format=img_format, quality=95)
    elif img_format == "PNG":
        image.save(image_bytes, format=img_format, compress_level=0)
    else:
        image.save(image_bytes, format=img_format)
    image_bytes.seek(0)

    s3.upload_fileobj(image_bytes, bucket, s3_key)





def delete_s3_keys(bucket, keys):
    delete_keys_objs = [{"Key": key} for key in keys]
    s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys_objs})





def avgSide(image):
    return (image.height + image.width) / 2


def representsInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def getCommand(word):
    word = word.lower()
    keywords = ["check", "scan"]

    for keyword in keywords:
        if word.startswith(keyword):

            cmd_suffix = word[len(keyword):]

            if cmd_suffix in ["", "this"]:
                return 1
            try:
                return int(cmd_suffix)
            except ValueError:
                pass



def convert_box(original_box, original_image, new_image):

    height_sf = new_image.height / original_image.height
    width_sf = new_image.width / original_image.width

    new_box = (original_box[0] * width_sf,
               original_box[1] * height_sf,
               original_box[2] * width_sf,
               original_box[3] * height_sf)

    return new_box


def resize_image(image, new_avg_side):

    avg_side = (image.height + image.width) / 2
    scale_factor = new_avg_side / avg_side

    new_height = round(image.height * scale_factor)
    new_width = round(image.width * scale_factor)

    new_image = image.resize(size=(new_width, new_height))
    return new_image


def log_sequence_token(log_group, log_stream):

    response = cloudwatch.describe_log_streams(
        logGroupName=log_group,
        logStreamNamePrefix=log_stream,
        limit=1)

    logstreams = response["logStreams"]
    logstream = next(x for x in logstreams if x["logStreamName"] == log_stream)

    try:
        token = logstream["uploadSequenceToken"]
    except KeyError:
        token = None

    return token


def cw_log(log_group, log_stream, text):

    while True:

        seq_token = log_sequence_token(log_group, log_stream)
        timestamp = int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp() * 1000)

        try:
            response = cloudwatch.put_log_events(
                    logGroupName=log_group,
                    logStreamName=log_stream,
                    logEvents=[{"timestamp": timestamp,
                                "message": text}],
                    sequenceToken="0" if seq_token is None else seq_token)

        except cloudwatch.exceptions.InvalidSequenceTokenException as e:
            print("Invalid sequence token when trying to log to cloudwatch, attempting to get a newer token.")
            continue
        except cloudwatch.exceptions.DataAlreadyAcceptedException as e:
            print("Data already logged apparently (should not have happened). Skipping.")

        break




def getList(filename):
    list = []
    with open(filename, "r") as file:
        for line in file:
            line = line.strip()
            if line != "":
                list.append(line)
    return list


def saveList(list, filename):
    with open(filename, "w") as f:
        for item in list:
            f.write(str(item) + "\n")


if __name__ == '__main__':
   pass